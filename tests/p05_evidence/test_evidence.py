"""P05 evidence tests: content addressing, bundle archive, WAL backup/restore.

Everything here uses real temporary files/directories (`tmp_path`) and the real
SHA-256 of the actual bytes; the only fakes are two explicitly test-only
objects (`_FailingStore`, `_SpyStore`) used to prove sink failures are reported
separately and that repair never re-ingests content. No test blocks on a
barrier/event, so a hung run cannot happen silently.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from project_kernel.contracts.dto import ArtifactRef, ObjectRef, ResolvedScope
from project_kernel.contracts.errors import KernelError, artifact_missing
from project_kernel.data.store.uow import UnitOfWork
from project_kernel.evidence.archive import (
    ArchiveManifest,
    BundleExporter,
    SinkLedger,
    SinkReceipt,
    archive_status,
)
from project_kernel.evidence.artifact_store import ArtifactStorage, ScopedArtifactStorage
from project_kernel.evidence.backup import (
    backup_create,
    restore_apply,
    restore_plan,
    restore_verify,
    verify_backup_file,
)

from p01_store.helpers import make_context, make_store, record_payload


def _publish(artifact_store: ArtifactStorage, data: bytes,
             media_type: str = "text/plain") -> ArtifactRef:
    staged = artifact_store.stage(data, media_type)
    return artifact_store.publish(staged, media_type)


def _ready_path(storage: ArtifactStorage, digest: str) -> Path:
    return storage.ready_root / digest[:2] / digest


def _manifest(artifacts, *, manifest_id: str = "m1", snapshot_digest: str = "b" * 64,
              operations=("op-1",), sinks=("exports",)) -> ArchiveManifest:
    return ArchiveManifest(manifest_id=manifest_id, snapshot_digest=snapshot_digest,
                           delivery_operation_refs=tuple(operations),
                           artifacts=tuple(artifacts), required_sinks=tuple(sinks))


class _SpyStore:
    """TEST-ONLY spy: records stage/publish/open_read to prove repair behaviour."""

    def __init__(self, real: ArtifactStorage):
        self.real = real
        self.calls: list[tuple[str, str | None]] = []

    def open_read(self, ref: ArtifactRef) -> bytes:
        self.calls.append(("open_read", ref.sha256))
        return self.real.open_read(ref)

    def verify(self, ref: ArtifactRef, **kwargs):
        self.calls.append(("verify", ref.sha256))
        return self.real.verify(ref, **kwargs)

    def stage(self, *args, **kwargs):
        self.calls.append(("stage", None))
        return self.real.stage(*args, **kwargs)

    def publish(self, *args, **kwargs):
        self.calls.append(("publish", None))
        return self.real.publish(*args, **kwargs)


# --------------------------------------------------------------- artifact store

def test_stage_publish_verify_roundtrip(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    data = b"hello kernel\n"
    staged = a.stage(data, "text/plain")
    assert staged.sha256 == hashlib.sha256(data).hexdigest()  # real digest of real bytes
    ref = a.publish(staged, "text/plain")
    assert ref.sha256 == staged.sha256
    assert ref.size_bytes == str(len(data))
    assert a.verify(ref)["ok"] is True
    assert a.open_read(ref) == data


def test_same_digest_is_verified_then_reused_without_rewrite(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    first = a.stage(b"same bytes", "text/plain")
    r1 = a.register(first.staged_locator, first.sha256, media_type="text/plain")
    assert r1.state == "ready" and r1.reused is False
    ready = _ready_path(a, r1.sha256)
    before = ready.stat().st_mtime_ns

    second = a.stage(b"same bytes", "text/plain")
    r2 = a.register(second.staged_locator, second.sha256, media_type="text/plain")
    assert r2.sha256 == r1.sha256
    assert r2.reused is True
    assert r2.state == "ready"
    assert r2.location is not None and r2.location.state == "ready"
    assert ready.stat().st_mtime_ns == before  # reused, never rewritten
    assert ready.read_bytes() == b"same bytes"


def test_modified_staging_file_is_rejected_on_publish(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    staged = a.stage(b"original", "text/plain")
    Path(a.root / staged.staged_locator).write_bytes(b"tampered!")  # changed after hashing
    with pytest.raises(KernelError) as exc:
        a.publish(staged, "text/plain")
    assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"
    assert not _ready_path(a, staged.sha256).exists()  # never marked ready


def test_register_rejects_declared_digest_that_does_not_match_bytes(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    staged = a.stage(b"real bytes", "text/plain")
    with pytest.raises(KernelError) as exc:
        a.register(staged.staged_locator, "0" * 64, media_type="text/plain")
    assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"
    assert a.quarantine_entries() == []


def test_register_accepts_object_ref_locator_and_rejects_escape(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    staged = a.stage(b"ref locator", "text/plain")
    record = a.register({"object_type": "staging", "object_id": staged.staged_locator.split("/")[1]},
                        staged.sha256, media_type="text/plain")
    assert record.state == "ready"
    with pytest.raises(KernelError) as exc:
        a.register("../outside/token", staged.sha256, media_type="text/plain")
    assert exc.value.error.code == "INVALID_INPUT"


def test_corrupt_store_entry_is_isolated_and_reported(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"good content")
    ready = _ready_path(a, ref.sha256)
    ready.write_bytes(b"corrupt")  # simulate storage corruption

    result = a.verify(ref)
    assert result["ok"] is False
    assert result["reason"] == "digest_mismatch"
    assert result["state"] == "unavailable"
    assert not ready.exists()  # corrupt content was moved aside, not overwritten
    entries = a.quarantine_entries()
    assert len(entries) == 1
    assert entries[0]["sha256"] == ref.sha256
    assert entries[0]["state"] == "unavailable"
    assert Path(entries[0]["quarantine_path"]).read_bytes() == b"corrupt"
    assert a.unavailable()[ref.sha256]["reason"] == "digest_mismatch"
    # the digest of the ArtifactRef was never rewritten
    assert ref.sha256 == hashlib.sha256(b"good content").hexdigest()


def test_publish_refuses_to_overwrite_different_bytes_for_same_digest(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"payload")
    ready = _ready_path(a, ref.sha256)
    ready.write_bytes(b"different")
    staged = a.stage(b"payload", "text/plain")
    with pytest.raises(KernelError) as exc:
        a.register(staged.staged_locator, staged.sha256, media_type="text/plain")
    assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"
    entry = a.quarantine_entries()[-1]
    assert entry["reason"] == "digest_mismatch"
    assert Path(entry["quarantine_path"]).read_bytes() == b"different"  # preserved, isolated
    # a fresh publish of the same digest now succeeds (no silent overwrite happened)
    redo = a.register(staged.staged_locator, staged.sha256, media_type="text/plain")
    assert redo.state == "ready" and redo.reused is False
    assert ready.read_bytes() == b"payload"


def test_missing_artifact_never_verifies(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = ArtifactRef("deadbeef", "a" * 64, "1", "text/plain", True)
    assert a.verify(ref)["ok"] is False
    assert a.verify(ref)["state"] == "missing"
    with pytest.raises(KernelError) as exc:
        a.open_read(ref)
    assert exc.value.error.code == "ARTIFACT_MISSING"


def test_require_ready_freeze_guard(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    good = _publish(a, b"required artifact")
    assert a.require_ready([good]) == (good,)

    missing = ArtifactRef("x", "b" * 64, "3", "text/plain", True)
    with pytest.raises(KernelError) as exc:
        a.require_ready([good, missing])
    assert exc.value.error.code == "ARTIFACT_MISSING"

    _ready_path(a, good.sha256).write_bytes(b"changed after publish")
    with pytest.raises(KernelError) as exc:
        a.require_ready([good])
    assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"


def test_scoped_artifact_port_checks_scope_and_resolves_object_refs(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    port = ScopedArtifactStorage(a, project_id="proj-a")
    good = ResolvedScope(project_id="proj-a", store_id="store-a", principal_id="user-1",
                         capabilities=frozenset(), mode="test")

    staged = port.stage(good, b"port payload", media_type="text/plain")
    with pytest.raises(KernelError) as exc:
        port.stage(ResolvedScope(project_id="proj-b", store_id="store-b",
                                 principal_id="user-2", capabilities=frozenset(),
                                 mode="test"), b"x")
    assert exc.value.error.code == "SCOPE_MISMATCH"

    ref = port.publish(good, port.staged_ref(staged), staged.sha256)
    assert ref.sha256 == staged.sha256
    assert port.verify(good, {"object_id": ref.artifact_id})["ok"] is True
    assert port.open_read(good, ObjectRef("proj-a", "artifact", ref.artifact_id, "ready")) \
        == b"port payload"
    with pytest.raises(KernelError) as exc:
        port.open_read(good, ObjectRef("proj-a", "artifact", "unknown-artifact", "ready"))
    assert exc.value.error.code == "REFERENCE_NOT_FOUND"

    source = tmp_path / "input.bin"
    source.write_bytes(b"real file stream")
    staged_file = port.stage(good, source)
    record = port.register(good, port.staged_ref(staged_file), staged_file.sha256,
                           media_type="application/octet-stream")
    assert record.state == "ready"
    assert record.size_bytes == str(len(b"real file stream"))
    assert a.open_read(record.to_ref()) == b"real file stream"


# --------------------------------------------------------------------- archive
def test_archive_export_and_repair(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"bundle payload")
    exports = BundleExporter(tmp_path / "exports", a)
    m = _manifest([ref])
    receipt = exports.export(m, "exports")
    assert receipt.state == "succeeded"
    assert receipt.verified is True
    assert receipt.digest == m.digest()
    manifest_file = tmp_path / "exports" / "m1" / "manifest.json"
    exported = tmp_path / "exports" / "m1" / "artifacts" / ref.sha256
    assert manifest_file.exists() and exported.exists()
    assert hashlib.sha256(exported.read_bytes()).hexdigest() == ref.sha256
    assert exports.ledger.state("m1", "exports") == "succeeded"

    r2 = exports.repair(m, "exports")
    assert r2.digest == m.digest()
    assert r2.state == "succeeded"
    assert r2.original_effect_id is None
    assert exports.persisted_receipt("m1", "exports")["state"] == "succeeded"


def test_archive_manifest_digest_excludes_shell(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"x")
    m = _manifest([ref])
    d1 = m.digest()
    body = m.body()
    assert m.digest() == d1
    assert "sink_receipt" not in body
    assert "lease" not in body
    # a receipt for the same manifest does not change the manifest digest
    exports = BundleExporter(tmp_path / "exports", a)
    receipt = exports.export(m, "exports")
    assert receipt.digest == d1


def test_archive_export_no_overwrite_different_manifest(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"x")
    exports = BundleExporter(tmp_path / "exports", a)
    m1 = _manifest([ref])
    exports.export(m1, "exports")
    m2 = ArchiveManifest(manifest_id="m1", snapshot_digest="c" * 64,
                         delivery_operation_refs=("op-2",), artifacts=(ref,),
                         required_sinks=("exports",))
    with pytest.raises(KernelError) as exc:
        exports.export(m2, "exports")
    assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"
    assert exports.ledger.state("m1", "exports") == "failed"
    # the original export is untouched
    on_disk = json.loads((tmp_path / "exports" / "m1" / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["snapshot_digest"] == "b" * 64


def test_archive_export_is_idempotent_for_same_digest(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"idempotent")
    exports = BundleExporter(tmp_path / "exports", a)
    m = _manifest([ref])
    first = exports.export(m, "exports")
    manifest_path = tmp_path / "exports" / "m1" / "manifest.json"
    stamp = manifest_path.stat().st_mtime_ns
    second = exports.export(m, "exports")
    assert first.digest == second.digest == m.digest()
    assert second.state == "succeeded" and second.verified is True
    assert manifest_path.stat().st_mtime_ns == stamp  # same manifest reused, not rewritten


def test_partial_export_is_repaired_without_reingesting_content(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"payload one")
    exports = BundleExporter(tmp_path / "exports", a)
    m = _manifest([ref])
    exports.export(m, "exports")
    exported = tmp_path / "exports" / "m1" / "artifacts" / ref.sha256

    exported.unlink()  # simulate an incomplete/partial sink flush
    spy = _SpyStore(a)
    repair_exporter = BundleExporter(tmp_path / "exports", spy, ledger=exports.ledger)
    receipt = repair_exporter.repair(m, "exports", original_effect_id="effect-1")
    assert receipt.state == "succeeded" and receipt.verified is True
    assert receipt.original_effect_id == "effect-1"
    assert exported.read_bytes() == b"payload one"
    assert receipt.digest == m.digest()  # manifest never changes
    assert [c for c in spy.calls if c[0] in ("stage", "publish")] == []  # no re-ingest, no tool run


def test_corrupt_exported_artifact_is_isolated_and_refilled(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"payload two")
    exports = BundleExporter(tmp_path / "exports", a)
    m = _manifest([ref])
    exports.export(m, "exports")
    exported = tmp_path / "exports" / "m1" / "artifacts" / ref.sha256
    exported.write_bytes(b"broken export")

    receipt = exports.repair(m, "exports", attempt=2)
    assert receipt.state == "succeeded" and receipt.attempts == 2
    assert exported.read_bytes() == b"payload two"
    quarantined = list((tmp_path / "exports" / "_quarantine").iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"broken export"
    assert (tmp_path / "exports" / "m1" / "manifest.json").exists()


def test_repair_refuses_a_different_manifest_digest(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"x")
    exports = BundleExporter(tmp_path / "exports", a)
    m1 = _manifest([ref])
    exports.export(m1, "exports")
    m2 = ArchiveManifest(manifest_id="m1", snapshot_digest="d" * 64,
                         delivery_operation_refs=("op-9",), artifacts=(ref,),
                         required_sinks=("exports",))
    with pytest.raises(KernelError) as exc:
        exports.repair(m2, "exports", original_effect_id="effect-2")
    assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"


def test_changed_content_produces_new_manifest_and_keeps_old_reference(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    old_ref = _publish(a, b"version one")
    exports = BundleExporter(tmp_path / "exports", a)
    m_old = _manifest([old_ref], manifest_id="m1")
    exports.export(m_old, "exports")

    new_ref = _publish(a, b"version two")  # evidence changed -> new digest
    m_new = m_old.with_artifacts([new_ref], delivery_operation_refs=("op-2",))
    assert m_new.manifest_id != m_old.manifest_id
    assert m_new.digest() != m_old.digest()
    assert new_ref.sha256 != old_ref.sha256

    receipt = exports.export(m_new, "exports")
    assert receipt.state == "succeeded"
    # old manifest/export reference retained and still verifies
    old_dir = tmp_path / "exports" / "m1"
    assert old_dir.exists()
    assert (old_dir / "artifacts" / old_ref.sha256).read_bytes() == b"version one"
    assert (tmp_path / "exports" / m_new.manifest_id / "manifest.json").exists()

    m_changed = exports.repair(m_old, "exports")
    assert m_changed.digest == m_old.digest()  # repair re-exports the old digest as-is


def test_archive_status_reports_acceptance_flush_and_sinks_separately(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"x")
    m = _manifest([ref], sinks=("exports", "session"))

    pending = archive_status(m)
    assert pending["overall"] == "export_pending"
    assert pending["acceptance"] == "pending" and pending["flush"] == "pending"
    assert pending["sinks"] == {"exports": "pending", "session": "pending"}

    ledger = SinkLedger()
    ledger.begin(m.manifest_id, "exports")
    assert ledger.state(m.manifest_id, "exports") == "running"
    ledger.settle(SinkReceipt(m.manifest_id, "exports", "succeeded", m.digest()))

    partial = archive_status(m, acceptance="accepted", source_flushed=False, ledger=ledger)
    assert partial["overall"] == "partial"  # required session flush not confirmed
    assert partial["flush"] == "pending"
    assert partial["sinks"]["exports"] == "succeeded"

    ledger.settle(SinkReceipt(m.manifest_id, "session", "succeeded", m.digest()))
    complete = archive_status(m, acceptance="accepted", source_flushed=True, ledger=ledger)
    assert complete["overall"] == "complete"
    assert complete["flush"] == "confirmed"

    not_accepted = archive_status(m, acceptance="pending", source_flushed=True, ledger=ledger)
    assert not_accepted["overall"] == "partial"

    no_sinks = archive_status(_manifest([ref], sinks=()), ledger=ledger)
    assert no_sinks["overall"] == "partial"


def test_sink_receipts_are_durable_and_gate_completeness(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"durable receipt")
    m = _manifest([ref], sinks=("exports",))
    BundleExporter(tmp_path / "exports", a).export(m, "exports")

    restarted = BundleExporter(tmp_path / "exports", a)  # fresh ledger, same exports root
    assert restarted.sink_states(m.manifest_id) == {"exports": "succeeded"}
    persisted = restarted.persisted_receipt(m.manifest_id, "exports")
    assert persisted is not None
    assert persisted["state"] == "succeeded" and persisted["verified"] is True
    assert persisted["digest"] == m.digest()

    status = archive_status(m, acceptance="accepted", source_flushed=True,
                            receipt_store=restarted.receipt_store)
    assert status["overall"] == "complete"

    _ready_path(a, ref.sha256).unlink()  # required artifact no longer ready
    gated = archive_status(m, acceptance="accepted", source_flushed=True,
                           artifacts_ready=False, receipt_store=restarted.receipt_store)
    assert gated["overall"] == "partial"
    assert gated["artifacts"] == "not_ready"


def test_export_rejects_a_sink_outside_the_allowed_range(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"x")
    exports = BundleExporter(tmp_path / "exports", a, allowed_sinks=("exports",))
    m = _manifest([ref], sinks=("exports",))
    with pytest.raises(KernelError) as exc:
        exports.export(m, "../arbitrary-write-path")
    assert exc.value.error.code == "PERMISSION_DENIED"
    assert not (tmp_path / "exports" / "m1").exists()
    assert exports.persisted_receipt(m.manifest_id, "../arbitrary-write-path") is None


def test_sink_ledger_state_machine_rejects_non_terminal_settle(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"x")
    m = _manifest([ref])
    ledger = SinkLedger()
    ledger.begin(m.manifest_id, "exports")
    ledger.begin(m.manifest_id, "exports")  # retry appends an attempt
    entry = ledger.entries(m.manifest_id)[0]
    assert entry["attempts"] == 2
    with pytest.raises(KernelError) as exc:
        ledger.settle(SinkReceipt(m.manifest_id, "exports", "running", m.digest()))
    assert exc.value.error.code == "INVALID_INPUT"


def test_failing_sink_is_reported_as_failed_not_success(tmp_path):
    """TEST-ONLY fake store: proves a sink failure is a reported failed receipt."""
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"unreadable in the fake sink")
    exports = BundleExporter(tmp_path / "exports", _UnreadableStore(a, ref.sha256))
    m = _manifest([ref])
    receipt = exports.export(m, "exports")
    assert receipt.state == "failed"
    assert receipt.verified is False
    assert receipt.error
    assert exports.ledger.state(m.manifest_id, "exports") == "failed"
    assert exports.persisted_receipt(m.manifest_id, "exports")["state"] == "failed"
    assert not (tmp_path / "exports" / "m1").exists()  # no half-published bundle
    status = archive_status(m, acceptance="accepted", source_flushed=True, ledger=exports.ledger)
    assert status["overall"] == "export_pending"


class _UnreadableStore:
    """TEST-ONLY fake: an artifact store whose read always fails."""

    def __init__(self, real: ArtifactStorage, digest: str):
        self.real = real
        self.digest = digest

    def open_read(self, ref: ArtifactRef) -> bytes:
        raise KernelError(artifact_missing("test-only sink read failure"))

    def verify(self, ref: ArtifactRef, **kwargs):
        return self.real.verify(ref, **kwargs)


# ---------------------------------------------------------------------- backup

def _seed(store, key: str = "bk-1") -> None:
    store.set_project_meta(store.project_id, store.store_id, "1.0.0", "2026-01-01T00:00:00Z")
    UnitOfWork(store, make_context(key=key), "test.command").execute(
        lambda h: h.records.append_revision("requirement", "r1", record_payload("t"),
                                            "requirement.v1"))


def test_wal_consistent_backup_with_integrity(tmp_path):
    store = make_store(tmp_path)
    try:
        _seed(store)
        wal = tmp_path / "proj-a.sqlite-wal"
        assert wal.exists()  # committed rows still live in the WAL, not checkpointed
        manifest = backup_create(store, tmp_path / "backups")
        assert manifest.integrity_ok is True
        assert manifest.foreign_keys_ok is True
        assert manifest.versions_ok is True
        assert manifest.references_ok is True
        assert manifest.all_ok is True
        backup_file = tmp_path / "backups" / f"{manifest.backup_id}.sqlite"
        assert backup_file.exists()
        assert manifest.file_sha256 == _sha256(backup_file)
        assert manifest.file_bytes == backup_file.stat().st_size
        conn = sqlite3.connect(str(backup_file))
        try:
            count = conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0]
        finally:
            conn.close()
        assert count == 1  # committed WAL content is present in the copy
        assert (tmp_path / "backups" / f"{manifest.backup_id}.manifest.json").exists()
        audit = (tmp_path / "backups" / "registry.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(audit[-1])["event"] == "backup.created"
        assert json.loads(audit[-1])["backup_id"] == manifest.backup_id
    finally:
        store.close()


def test_backup_reports_versions_references_and_artifact_manifest(tmp_path):
    a = ArtifactStorage(tmp_path / "artifacts")
    ref = _publish(a, b"artifact to back up")
    store = make_store(tmp_path)
    try:
        _seed(store)
        manifest = backup_create(store, tmp_path / "backups",
                                 artifact_manifest=(ref,), artifact_store=a)
        assert manifest.artifacts_ok is True
        assert manifest.artifact_problems == ()

        _ready_path(a, ref.sha256).unlink()  # artifact bytes lost
        broken = backup_create(store, tmp_path / "backups",
                               artifact_manifest=(ref,), artifact_store=a)
        assert broken.artifacts_ok is False
        assert any("missing" in p for p in broken.artifact_problems)
        assert broken.all_ok is False
    finally:
        store.close()


def test_backup_detects_tampered_version_and_reference(tmp_path):
    store = make_store(tmp_path)
    try:
        _seed(store)
        manifest = backup_create(store, tmp_path / "backups")
        good_copy = tmp_path / "backups" / f"{manifest.backup_id}.sqlite"
        copy = tmp_path / "tampered.sqlite"
        copy.write_bytes(good_copy.read_bytes())

        conn = sqlite3.connect(str(copy))
        try:
            conn.execute("UPDATE project_meta SET schema_version='9.9.9'")
            conn.execute("DELETE FROM schema_migration WHERE migration_id='0003_legacy_knowledge_tables'")
            conn.execute(
                "INSERT INTO entity_head (project_id, type, object_id, pointer_name,"
                " revision_id, head_version, updated_seq)"
                " VALUES ('proj-a','requirement','orphan','current','missing-rev',1,1)")
            conn.commit()
        finally:
            conn.close()

        checks = verify_backup_file(copy, expected_schema_version="1.0.0", source_conn=store.conn)
        assert checks["integrity_ok"] is True
        assert checks["versions_ok"] is False
        assert checks["schema_version"] == "9.9.9"
        assert any("schema_version" in p for p in checks["version_problems"])
        assert any("migration" in p for p in checks["version_problems"])
        assert checks["references_ok"] is False
        assert any("entity_head -> revision" in p for p in checks["reference_problems"])

        # the orphan head also violates the revision FK, so foreign_key_check catches it
        fk_recheck = verify_backup_file(copy, expected_schema_version="1.0.0", source_conn=store.conn)
        assert fk_recheck["foreign_keys_ok"] is False
    finally:
        store.close()


def test_corrupt_backup_file_fails_integrity_check(tmp_path):
    store = make_store(tmp_path)
    try:
        _seed(store)
        manifest = backup_create(store, tmp_path / "backups")
        backup_file = tmp_path / "backups" / f"{manifest.backup_id}.sqlite"
        data = bytearray(backup_file.read_bytes())
        data[100] ^= 0xFF  # corrupt the sqlite_master page of the copy
        backup_file.write_bytes(bytes(data))
        checks = verify_backup_file(backup_file)
        assert checks["integrity_ok"] is False
        assert len(manifest.file_sha256) == 64
        assert manifest.file_sha256 != _sha256(backup_file)
    finally:
        store.close()


def test_restore_plan_distinguishes_business_vs_disaster():
    business = restore_plan("business", "rev-1")
    assert business.restore_kind == "business_revision"
    assert business.mode == "new_revision"
    assert business.requires_writer_fence is False
    assert business.requires_human_decision is False
    assert business.preserve_history is True
    assert business.apply_implemented is False

    alias = restore_plan("business_revision", "rev-1")
    assert alias.plan_id == business.plan_id
    assert business.digest() == alias.digest()

    disaster = restore_plan("disaster", "bkp-1", reason="disk failure")
    assert disaster.restore_kind == "disaster_recovery"
    assert disaster.mode == "replace_store"
    assert disaster.requires_writer_fence is True
    assert disaster.requires_human_decision is True
    assert disaster.preserve_history is True
    assert "fence held" in " ".join(disaster.verification_steps)
    assert restore_plan("disaster_recovery", "bkp-1", reason="disk failure").plan_id == disaster.plan_id

    with pytest.raises(KernelError) as exc:
        restore_plan("nonsense", "x")
    assert exc.value.error.code == "INVALID_INPUT"


def test_restore_apply_fence_semantics_and_never_fakes_success(tmp_path):
    store = make_store(tmp_path)
    try:
        _seed(store)
        manifest = backup_create(store, tmp_path / "backups")
        backup_file = tmp_path / "backups" / f"{manifest.backup_id}.sqlite"
        plan = restore_plan("disaster", manifest.backup_id, reason="test")

        # no human decision -> refused
        with pytest.raises(KernelError) as exc:
            restore_apply(plan, backup_path=backup_file)
        assert exc.value.error.code == "APPROVAL_REQUIRED"

        # no writer fence -> refused (never a partial swap)
        with pytest.raises(KernelError) as exc:
            restore_apply(plan, human_decision_ref="decision-1", backup_path=backup_file)
        assert exc.value.error.code == "CAPABILITY_UNAVAILABLE"

        receipt = restore_apply(plan, human_decision_ref="decision-1",
                                writer_fence="fence-token", backup_path=backup_file,
                                audit_path=tmp_path / "restore-audit.jsonl")
        assert receipt.status == "not_implemented"
        assert receipt.implemented is False
        assert receipt.writer_fence_held is True
        assert receipt.mode == "replace_store"
        assert "never replaced" in receipt.note
        assert receipt.verification is not None and receipt.verification["ok"] is True
        payload = receipt.to_dict()
        assert payload["status"] != "applied"
        lines = (tmp_path / "restore-audit.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[-1])["event"] == "restore.recorded"
        assert json.loads(lines[-1])["status"] == "not_implemented"
    finally:
        store.close()


def test_restore_verify_and_business_apply_are_explicitly_not_implemented(tmp_path):
    store = make_store(tmp_path)
    try:
        _seed(store)
        manifest = backup_create(store, tmp_path / "backups")
        backup_file = tmp_path / "backups" / f"{manifest.backup_id}.sqlite"
        plan = restore_plan("disaster_recovery", manifest.backup_id, reason="verify")
        verified = restore_verify(plan, backup_file, expected_schema_version="1.0.0")
        assert verified["ok"] is True
        assert verified["integrity_ok"] is True and verified["references_ok"] is True

        business = restore_plan("business_revision", "rev-7", reason="user error")
        receipt = restore_apply(business)
        assert receipt.status == "not_implemented"
        assert receipt.implemented is False
        assert receipt.mode == "new_revision"
        assert receipt.verification is None
    finally:
        store.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
