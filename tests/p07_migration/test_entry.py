"""Normal application entry for explicitly configured synthetic imports."""
from __future__ import annotations

from dataclasses import replace

import pytest

from project_kernel.application.legacy_service import LegacyImportEntry, snapshot_digest
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import CommandContext, ObjectRef, ResolvedScope
from project_kernel.contracts.errors import KernelError
from project_kernel.data.store.uow import UnitOfWork
from project_kernel.migration.legacy import (LegacyRecord, LegacySnapshot,
    LegacySourceManifest, TableCount, FileEntry)
from project_kernel.migration.legacy.manifest import _utc_now

from .helpers import make_store, count


class SnapshotProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    def read_snapshot(self, ref):
        self.calls += 1
        assert ref == self.snapshot.ref
        return self.snapshot


def _ctx(store, key="import", *, caps=frozenset({"project.admin"}), mode="test", payload=None):
    scope = ResolvedScope(store.project_id, store.store_id, "operator", caps, mode)
    hash_input = payload if payload is not None else {"key": key}
    return CommandContext(scope, "cmd", key, sha256_digest(hash_input))


def _publish(store, kind, oid, payload, *, principal="operator"):
    ctx = _ctx(store, "seed-" + kind + "-" + oid)
    ctx = replace(ctx, scope=replace(ctx.scope, principal_id=principal))
    refs = []
    def cb(h):
        head = store.get_head(kind, oid, "current")
        ref = h.records.append_revision(kind, oid, payload, kind + ".v1")
        h.records.publish_head(ref, "current", str(head["head_version"]) if head else None)
        refs.append(ref)
        h.outcome.object_refs = (ref,)
    assert UnitOfWork(store, ctx, "system.ingest").execute(cb).status == "committed"
    return refs[0]


def _setup(tmp_path):
    store = make_store(tmp_path)
    records = (
        LegacyRecord("project", "p1", sha256_digest({"legacy_id": "p1"}), {"legacy_id": "p1"}),
        LegacyRecord("task", "t1", sha256_digest({"legacy_id": "t1", "project_id": "p1"}),
                     {"legacy_id": "t1", "project_id": "p1"},
                     owner_project_ref="p1", parent_refs=("p1",)),
        LegacyRecord("task", "orphan", sha256_digest({"legacy_id": "orphan", "project_id": "missing"}),
                     {"legacy_id": "orphan", "project_id": "missing"},
                     owner_project_ref="missing", parent_refs=("missing",)),
    )
    manifest = LegacySourceManifest("source-a", "synthetic://snapshot",
        (FileEntry("sample.jsonl", "d" * 64, 10),), (TableCount("tasks", 2),), _utc_now())
    snapshot_ref = _publish(store, "legacy_source_snapshot", "snap-a", {
        "source_store_id": "source-a", "manifest_digest": manifest.digest,
        "snapshot_digest": snapshot_digest("source-a", manifest, records)}, principal="producer")
    snapshot = LegacySnapshot(snapshot_ref, snapshot_digest("source-a", manifest, records),
                              "source-a", records, manifest, "producer")
    plan_ref = _publish(store, "legacy_import_plan", "plan-a", {
        "source_snapshot_ref": snapshot_ref.to_dict(), "target_project_id": store.project_id,
        "target_store_id": store.store_id, "source_store_id": "source-a",
        "project_mapping": {"p1": store.project_id}, "manifest_digest": manifest.digest,
        "batch_id": "batch-a"})
    provider = SnapshotProvider(snapshot)
    service = LegacyImportEntry(store, snapshot_provider=provider,
        trusted_snapshot_producers={"producer": {"source-a"}})
    payload = {"source_snapshot_ref": snapshot_ref.to_dict(), "import_plan_ref": plan_ref.to_dict()}
    return store, service, provider, payload


def _count(store, table):
    columns = {row[1] for row in store.conn.execute(f"PRAGMA table_info({table})")}
    if "project_id" in columns:
        return store.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?",
                                  (store.project_id,)).fetchone()[0]
    return store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_import_entry_persists_facts_quarantine_report_atomically_and_replays(tmp_path):
    store, service, provider, payload = _setup(tmp_path)
    try:
        original_snapshot = provider.snapshot
        first = service.import_legacy(_ctx(store), payload)
        assert first.status == "accepted"
        assert first.operation_id
        before = {table: _count(store, table) for table in
                  ("revision", "entity", "commit_log", "audit_event", "command_receipt")}
        replay = service.import_legacy(_ctx(store), payload)
        assert replay == first
        assert {table: _count(store, table) for table in before} == before
        report = store.get_revision(first.object_refs[-1])["payload"]
        assert report["status"] == "completed"
        assert report["imported"] == 2
        assert report["quarantined"] == 1
        assert store.conn.execute("SELECT COUNT(*) FROM revision WHERE project_id=? AND type='legacy_quarantine'",
                                  (store.project_id,)).fetchone()[0] == 1
        assert provider.snapshot == original_snapshot
        assert provider.calls == 1
    finally:
        store.close()


def test_import_requires_project_admin_and_test_mode(tmp_path):
    store, service, _, payload = _setup(tmp_path)
    try:
        before = _count(store, "revision")
        with pytest.raises(KernelError):
            service.import_legacy(_ctx(store, "denied", caps=frozenset()), payload)
        with pytest.raises(KernelError):
            service.import_legacy(_ctx(store, "production", mode="production"), payload)
        assert _count(store, "revision") == before
    finally:
        store.close()


def test_import_conflicting_key_hash_is_rejected_without_writes(tmp_path):
    store, service, _, payload = _setup(tmp_path)
    try:
        first = service.import_legacy(_ctx(store), payload)
        plan_payload = store.get_revision(ObjectRef.from_dict(payload["import_plan_ref"]))["payload"]
        changed_plan = {**plan_payload, "batch_id": "batch-other"}
        other_ref = _publish(store, "legacy_import_plan", "plan-other", changed_plan)
        changed = {**payload, "import_plan_ref": other_ref.to_dict()}
        before = _count(store, "revision")
        with pytest.raises(KernelError):
            service.import_legacy(_ctx(store, payload=changed), changed)
        assert _count(store, "revision") == before
        assert service.import_legacy(_ctx(store), payload) == first
    finally:
        store.close()


def test_import_same_key_different_payload_conflicts_before_provider_or_writes(tmp_path):
    store, service, provider, payload = _setup(tmp_path)
    try:
        service.import_legacy(_ctx(store), payload)
        before = _count(store, "revision")
        changed_ref = dict(payload["import_plan_ref"], revision_id="rev-404")
        changed = {**payload, "import_plan_ref": changed_ref}
        with pytest.raises(KernelError):
            service.import_legacy(_ctx(store, payload=changed), changed)
        assert provider.calls == 1
        assert _count(store, "revision") == before
    finally:
        store.close()


def test_import_replay_survives_store_restart_without_rereading_source(tmp_path):
    store, service, provider, payload = _setup(tmp_path)
    receipt = service.import_legacy(_ctx(store), payload)
    provider_calls = provider.calls
    database = store.conn.execute("PRAGMA database_list").fetchone()[2]
    store.close()
    from project_kernel.data.store.store import Store
    reopened = Store.open_project(database, "proj-a", "store-a")
    try:
        restarted = LegacyImportEntry(store=reopened, snapshot_provider=provider,
            trusted_snapshot_producers={"producer": {"source-a"}})
        assert restarted.import_legacy(_ctx(reopened), payload) == receipt
        assert provider.calls == provider_calls
        assert reopened.conn.execute("SELECT COUNT(*) FROM revision WHERE project_id=? AND type='imported_fact'",
                                     (reopened.project_id,)).fetchone()[0] == 2
    finally:
        reopened.close()


def test_provider_failure_leaves_no_success_receipt_or_partial_import(tmp_path):
    store, service, provider, payload = _setup(tmp_path)
    try:
        def fail(_ref):
            raise OSError("snapshot provider unavailable")
        provider.read_snapshot = fail
        with pytest.raises(OSError):
            service.import_legacy(_ctx(store), payload)
        assert store.get_receipt("operator", "import") is None
        assert store.conn.execute("SELECT COUNT(*) FROM revision WHERE project_id=? AND type='imported_fact'",
                                  (store.project_id,)).fetchone()[0] == 0
    finally:
        store.close()


@pytest.mark.parametrize("mutation", ["provider_ref", "producer", "digest", "target", "mapping"])
def test_import_rejects_snapshot_or_plan_mismatch_before_writes(tmp_path, mutation):
    store, service, provider, payload = _setup(tmp_path)
    try:
        if mutation == "provider_ref":
            provider.snapshot = replace(provider.snapshot,
                ref=ObjectRef("proj-a", "legacy_source_snapshot", "other", "rev-1"))
            provider.read_snapshot = lambda ref: provider.snapshot
        elif mutation == "producer":
            provider.snapshot = replace(provider.snapshot, producer_principal_id="attacker")
        elif mutation == "digest":
            provider.snapshot = replace(provider.snapshot, digest="0" * 64)
        else:
            old = store.get_revision(ObjectRef.from_dict(payload["import_plan_ref"]))["payload"]
            changed = dict(old)
            changed["target_project_id" if mutation == "target" else "project_mapping"] = (
                "other-project" if mutation == "target" else {"p1": "other-project"})
            plan_ref = _publish(store, "legacy_import_plan", "plan-" + mutation, changed)
            payload = {**payload, "import_plan_ref": plan_ref.to_dict()}
        before = _count(store, "revision")
        with pytest.raises(KernelError):
            service.import_legacy(_ctx(store, "bad-" + mutation), payload)
        assert _count(store, "revision") == before
    finally:
        store.close()
