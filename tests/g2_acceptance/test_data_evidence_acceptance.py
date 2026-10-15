"""Independent G2 data/evidence cases through project-bound test RPC entries."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

import pytest

from project_kernel.application.environment_service import PythonEnvironmentProbe
from project_kernel.application.legacy_service import snapshot_digest
from project_kernel.application.recovery_authorization import authorize_restore
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import ObjectRef
from project_kernel.contracts.errors import KernelError
from project_kernel.data.queries.service import QueryService
from project_kernel.data.store.store import Store
from project_kernel.evidence import ArtifactStorage, BundleExporter
from project_kernel.evidence.archive import SinkReceipt
from project_kernel.evidence.provider import IsolatedRestoreTarget
from project_kernel.evidence.recovery import ControlledStoreRecovery, ControlledStoreRestoreTarget
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.migration.legacy import LegacyReader, LegacySnapshot
from project_kernel.migration.legacy.manifest import build_source_manifest

from p01_store.helpers import make_store
from p02_design.helpers import context, prepare_dispatch, seed
from p07_migration.helpers import make_legacy_source
from p13_integration.auth_helpers import build_test_server
from p13_integration.test_closed_loop import FileCheckProvider, RecordedExecutor, latest


class Capture:
    """Keep complete legal RPC messages and summaries inside one pytest root."""

    def __init__(self, root, nodeid):
        self.root = root
        self.data = {"nodeid": nodeid, "mode": "test_non_dsh", "root": str(root.resolve()),
                     "rpc": [], "host_seeds": [], "observations": {}}

    def raw(self, server, name, payload, key=None, *, query=False, entry="machine", **extra):
        params = {"protocol_version": "1.0.0", "invocation_context_id": "ctx1",
                  "selector": {"project_id": "proj-a"}, "payload": payload}
        if query:
            params["query"] = name
        else:
            params.update(command=name, expected_heads=[], idempotency_key=key or name)
        params.update(extra)
        request = {"jsonrpc": "2.0", "id": "g2-data", "method":
                   "kernel.query" if query else "kernel.command", "params": params}
        response = decode_frame(server.handle_line(encode_frame(request)))
        self.data["rpc"].append({"entry": entry, "request": request, "response": response})
        return response

    def command(self, server, name, payload, key=None, *, allow_rejected=False, **extra):
        response = self.raw(server, name, payload, key, **extra)
        assert "error" not in response, response
        receipt = response["result"]["receipt"]
        if not allow_rejected:
            assert receipt["status"] != "rejected", receipt
        return receipt

    def query(self, server, name, payload=None, **extra):
        response = self.raw(server, name, payload or {}, query=True, **extra)
        assert "error" not in response, response
        return response["result"]

    def host_seed(self, store, kind, oid, body):
        ref = seed(store, kind, oid, body)
        self.data["host_seeds"].append({"ref": ref.to_dict(), "payload": body,
                                         "digest": store.get_revision(ref)["digest"]})
        return ref

    def save(self, store=None):
        if store is not None:
            self.data["store"] = {"project_id": store.project_id, "store_id": store.store_id,
                                  "head_seq": str(store.next_commit_seq() - 1)}
            self.data["host_configuration"] = {
                kind: QueryService(store).latest_revisions(kind) for kind in
                ("budget", "network_policy", "execution_root", "recipe", "design_decision",
                 "candidate_manifest", "delivery_target", "store", "policy")}
        files = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and not path.name.endswith("-evidence.json"):
                raw = path.read_bytes()
                files.append({"path": str(path.relative_to(self.root)), "size_bytes": len(raw),
                              "sha256": hashlib.sha256(raw).hexdigest(),
                              "database_bytes_not_archived": path.suffix == ".sqlite"
                              or path.name.endswith(("-wal", "-shm"))})
        self.data["files"] = files
        (self.root / "data-evidence.json").write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _delivered(root, capture):
    store = make_store(root)
    storage = ArtifactStorage(root / "artifacts")
    exporter = BundleExporter(root / "exports", storage, allowed_sinks=("exports",))
    executor = RecordedExecutor()
    checks = FileCheckProvider(store, storage)
    server = build_test_server(store, executor=executor, artifact_root=root / "artifacts",
        bundle_exporter=exporter, check_provider=checks, environment_provider=PythonEnvironmentProbe(),
        evidence_config={"exporters": {"exports": exporter}, "trusted_staging_principals": ["user-1"]},
        source_bindings={"user-1": [("test-host", "session", "1")]})
    human = build_test_server(store, human=True)
    invoke = lambda name, body, key: capture.command(server, name, body, key)
    prepared = prepare_dispatch(store, root, strategies=("s2",), invoke=invoke)
    started = invoke("attempt.start", {"packet_ref": prepared["packet"].to_dict(), "strategy_id": "s2",
        "execution_root_ref": prepared["roots"]["s2"].to_dict()}, "start")
    attempt = latest(store, "attempt", started["operation_id"])
    raw = (root / "s2" / "output.txt").read_bytes()
    artifact = storage.publish(storage.stage(raw, "text/plain"), "text/plain")
    candidate = capture.host_seed(store, "candidate_manifest", "candidate", {
        "attempt_ref": attempt.to_dict(), "candidate_digest": hashlib.sha256(raw).hexdigest(),
        "artifacts": [artifact.to_dict()]})
    invoke("verification.run", {"attempt_ref": attempt.to_dict(), "candidate_manifest_ref": candidate.to_dict(),
        "acceptance_refs": [prepared["acceptance"].to_dict()]}, "verify")
    selection = invoke("attempt.select", {"attempt_ref": attempt.to_dict(), "comparison_refs": [attempt.to_dict()],
        "purpose": "delivery", "reason": "test file verified"}, "select")["object_refs"][0]
    target = capture.host_seed(store, "delivery_target", "target", {"method": "bundle", "sink_id": "exports"})
    requested = invoke("delivery.request", {"selection_ref": selection, "candidate_ref": candidate.to_dict(),
        "target_ref": target.to_dict()}, "request")
    approval = store.get_revision(ObjectRef.from_dict(requested["object_refs"][0]))["payload"]
    capture.command(human, "approval.decide", {"approval_id": approval["approval_id"],
        "snapshot_digest": approval["snapshot_digest"], "decision": "approved", "reason": "test identity reviewed bytes"},
        "approve", entry="human")
    applied = invoke("delivery.apply", {"approval_id": approval["approval_id"],
        "snapshot_digest": approval["snapshot_digest"]}, "apply")
    operation = latest(store, "delivery", applied["operation_id"])
    assert store.get_revision(operation)["payload"]["status"] == "applied"
    return store, server, human, storage, exporter, executor, prepared, operation


def _source_event(store, server, storage, capture, sequence):
    source = capture.host_seed(store, "source", "host", {"host_id": "test-host"})
    policy = capture.host_seed(store, "policy", "retain", {"mode": "test"})
    body = {"text": "synthetic source " + str(sequence)}
    staged = storage.stage(json.dumps(body).encode(), "application/json")
    locator = capture.host_seed(store, "staging", "stage-" + str(sequence), {
        "locator": staged.staged_locator, "digest": staged.sha256})
    registered = capture.command(server, "artifact.register", {
        "trusted_staged_locator_ref": locator.to_dict(), "digest": staged.sha256,
        "source_ref": source.to_dict(), "media_type": "application/json", "retention_policy_ref": policy.to_dict()},
        "register-source-" + str(sequence))
    operation = capture.query(server, "operation.status", {"operation_id": registered["operation_id"]})["data"]
    artifact = store.get_revision(ObjectRef.from_dict(operation["result_refs"][0]))["payload"]["artifact"]
    return capture.command(server, "source.ingest", {
        "source_stream": {"host_id": "test-host", "origin_session_id": "session", "log_generation": "1"},
        "events": [{"source_seq": str(sequence), "payload_hash": sha256_digest(body), "schema_version": "1.0.0",
                    "payload_artifact_ref": artifact, "evidence_mode": "test"}],
        "observed_range": {"first": str(sequence), "last": str(sequence), "truncated": False}},
        "ingest-source-" + str(sequence))


def test_ac27_rpc_concurrent_close_and_repair_without_execution(tmp_path, request, monkeypatch):
    capture = Capture(tmp_path, request.node.nodeid)
    store, server, _, storage, exporter, executor, prepared, operation = _delivered(tmp_path, capture)
    try:
        barrier = threading.Barrier(2, timeout=10)
        database = Path(store.conn.execute("PRAGMA database_list").fetchone()[2])
        payload = {"task_ref": prepared["task"].to_dict(), "applied_operation_ref": operation.to_dict()}
        def close_once(key):
            connection = Store.open_project(database, "proj-a", "store-a")
            try:
                entry = build_test_server(connection, artifact_root=tmp_path / "artifacts", bundle_exporter=exporter)
                barrier.wait()
                return capture.command(entry, "task.close", payload, key, allow_rejected=True)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(close_once, key) for key in ("close-a", "close-b")]
            receipts = [future.result(timeout=20) for future in futures]
        assert sorted(item["status"] for item in receipts) == ["committed", "rejected"]
        committed = next(item for item in receipts if item["status"] == "committed")
        manifest_ref = committed["object_refs"][1]
        assert len(QueryService(store).latest_revisions("archive_manifest")) == 1
        assert store.conn.execute("SELECT COUNT(*) FROM audit_event WHERE event_type='task.closed'").fetchone()[0] == 1
        exported = capture.command(server, "archive.export", {"manifest_ref": manifest_ref, "sink_id": "exports"}, "archive")
        path = tmp_path / "exports" / manifest_ref["object_id"]
        manifest_bytes = (path / "manifest.json").read_bytes()
        artifact_path = next((path / "artifacts").iterdir())
        expected = artifact_path.read_bytes()
        artifact_path.unlink()
        monkeypatch.setattr(executor, "run", lambda *args: pytest.fail("repair executed an attempt"))
        repaired = capture.command(server, "archive.repair", {"manifest_ref": manifest_ref, "sink_id": "exports",
            "original_effect_id": exported["operation_id"]}, "repair")
        result = capture.query(server, "operation.status", {"operation_id": repaired["operation_id"]})["data"]
        assert result["status"] == "succeeded"
        assert artifact_path.read_bytes() == expected
        assert (path / "manifest.json").read_bytes() == manifest_bytes
        assert executor.calls == 1
        wrong = capture.command(server, "archive.repair", {"manifest_ref": manifest_ref, "sink_id": "exports",
            "original_effect_id": "missing-operation"}, "wrong-repair", allow_rejected=True)
        assert wrong["status"] == "rejected" and wrong["error"]["code"] == "INVALID_INPUT"
        capture.data["observations"].update(close_receipts=receipts, manifest_ref=manifest_ref,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(), executor_calls=executor.calls)
    finally:
        capture.save(store)
        store.close()


def test_ac28_rpc_sink_failure_and_local_source_gap_repair(tmp_path, request, monkeypatch):
    capture = Capture(tmp_path, request.node.nodeid)
    store, server, _, storage, exporter, executor, prepared, operation = _delivered(tmp_path, capture)
    try:
        _source_event(store, server, storage, capture, 2)
        closed = capture.command(server, "task.close", {"task_ref": prepared["task"].to_dict(),
            "applied_operation_ref": operation.to_dict()}, "close")
        manifest_ref = closed["object_refs"][1]
        manifest_row = store.get_revision(ObjectRef.from_dict(manifest_ref))
        original_export = exporter.export
        monkeypatch.setattr(exporter, "export", lambda manifest, sink, **kw:
            SinkReceipt(manifest.manifest_id, sink, "failed", manifest.digest(), error="test file sink offline"))
        failed = capture.command(server, "archive.export", {"manifest_ref": manifest_ref, "sink_id": "exports"}, "export-failed")
        failed_status = capture.query(server, "archive.status", {"manifest_ref": manifest_ref})
        assert failed_status["data"]["main_store"]["store_id"] == "store-a"
        assert failed_status["data"]["sinks"][0]["state"] == "failed"
        assert failed_status["data"]["archive_states"][0]["source_flushed"] is False
        assert failed_status["source_watermarks"]["data_state"] == "gapped"
        assert failed_status["data"]["session_flush"]["state"] == "not_configured"
        monkeypatch.setattr(exporter, "export", original_export)
        repaired = capture.command(server, "archive.repair", {"manifest_ref": manifest_ref, "sink_id": "exports",
            "original_effect_id": failed["operation_id"]}, "repair-file")
        file_only = capture.query(server, "archive.status", {"manifest_ref": manifest_ref})
        assert file_only["data"]["sinks"][0]["state"] == "succeeded"
        assert file_only["data"]["archive_states"][0]["overall"] == "partial"
        assert file_only["data"]["partial"] is True
        _source_event(store, server, storage, capture, 1)
        repaired = capture.command(server, "archive.repair", {"manifest_ref": manifest_ref, "sink_id": "exports",
            "original_effect_id": repaired["operation_id"]}, "repair-contiguous-source")
        final = capture.query(server, "archive.status", {"manifest_ref": manifest_ref})
        assert final["data"]["archive_states"][0]["overall"] == "complete"
        assert final["data"]["partial"] is False
        assert final["source_watermarks"]["data_state"] == "ok"
        assert final["data"]["session_flush"]["state"] == "not_configured"
        assert store.get_revision(ObjectRef.from_dict(manifest_ref)) == manifest_row
        assert executor.calls == 1
        capture.data["observations"].update(manifest_ref=manifest_ref, manifest_digest=manifest_row["digest"],
            failed_status=failed_status, file_only=file_only, repaired_status=final, executor_calls=executor.calls,
            source_flush_limit="local continuous ingestion only; no host final-flush proof")
    finally:
        capture.save(store)
        store.close()


@pytest.mark.parametrize("false_at", ["close", "sink_callback"])
def test_ac28_explicit_false_source_flush_stays_partial(tmp_path, request, false_at):
    from p04_delivery.helpers import Harness, ctx
    capture = Capture(tmp_path, request.node.nodeid)
    harness = Harness(tmp_path)
    try:
        harness.to_delivery_ready()
        operation, _, _ = harness.applied()
        closed = harness.svc.task_close(ctx("close"), harness.task_ref, operation,
                                        source_flushed=false_at != "close")
        manifest_ref = closed.object_refs[1].to_dict()
        if false_at == "sink_callback":
            manifest = harness.store.get_revision(closed.object_refs[1])
            callback = harness.svc.record_sink_result(ctx("callback"), harness.task_ref.object_id,
                "exports", "succeeded", digest=manifest["digest"], verified=True, source_flushed=False)
            assert callback.status == "committed"
        server = build_test_server(harness.store, artifact_root=tmp_path / "artifacts",
            evidence_config={"exporters": {"exports": harness.exporter}})
        capture.command(server, "archive.export", {"manifest_ref": manifest_ref, "sink_id": "exports"}, "export")
        result = capture.query(server, "archive.status", {"manifest_ref": manifest_ref})
        assert result["data"]["archive_states"][0]["source_flushed"] is False
        assert result["data"]["archive_states"][0]["overall"] == "partial"
        assert result["data"]["partial"] is True
        capture.data["observations"]["explicit_false_not_promoted"] = result
    finally:
        capture.save(harness.store)
        harness.close()


def test_ac29_rpc_wal_backup_and_fenced_test_store_recovery(tmp_path, request):
    capture = Capture(tmp_path, request.node.nodeid)
    store = make_store(tmp_path)
    storage = ArtifactStorage(tmp_path / "artifacts")
    target = ControlledStoreRestoreTarget(tmp_path / "proj-a.sqlite", "controlled-test")
    server = build_test_server(store, artifact_root=tmp_path / "artifacts", evidence_config={
        "backup_root": tmp_path / "backups", "restore_target": target})
    human = build_test_server(store, human=True)
    recovery = ControlledStoreRecovery(target, project_id="proj-a", store_id="store-a",
        backup_root=tmp_path / "backups", audit_root=tmp_path / "maintenance-audit",
        artifact_storage=storage, authorize_restore=authorize_restore)
    try:
        store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        store.conn.execute("PRAGMA wal_autocheckpoint=0")
        original = capture.command(server, "task.create", {"title": "committed-WAL", "goal": "backup includes WAL",
            "requirement_refs": [], "mode": "test"}, "wal-task")["object_refs"][0]
        wal = tmp_path / "proj-a.sqlite-wal"
        assert wal.is_file() and wal.stat().st_size > 0
        baseline = sqlite3.connect(f"file:{target.live_path.as_posix()}?mode=ro&immutable=1", uri=True)
        try:
            assert baseline.execute("SELECT COUNT(*) FROM revision WHERE type='task'").fetchone()[0] == 0
        finally:
            baseline.close()
        store_ref = capture.host_seed(store, "store", "store-a", {"store_id": "store-a"})
        policy = capture.host_seed(store, "policy", "backup", {"mode": "test"})
        backup = capture.command(server, "backup.create", {"store_ref": store_ref.to_dict(),
            "policy_ref": policy.to_dict()}, "backup")
        backup_state = capture.query(server, "operation.status", {"operation_id": backup["operation_id"]})["data"]
        assert backup_state["status"] == "succeeded"
        backup_ref = backup_state["result_refs"][0]
        manifest = store.get_revision(ObjectRef.from_dict(backup_ref))["payload"]
        assert manifest["all_ok"]
        assert all(manifest[field] for field in ("integrity_ok", "foreign_keys_ok", "versions_ok", "references_ok", "artifacts_ok"))
        copied = sqlite3.connect(manifest["backup_path"])
        try:
            assert copied.execute("SELECT COUNT(*) FROM revision WHERE type='task'").fetchone()[0] == 1
        finally:
            copied.close()
        assert hashlib.sha256(Path(manifest["backup_path"]).read_bytes()).hexdigest() == manifest["file_sha256"]
        plan = capture.command(server, "restore.plan", {"revision_or_backup_ref": backup_ref,
            "restore_kind": "disaster_recovery", "reason": "isolated test-store maintenance rehearsal"}, "plan")
        plan_ref = ObjectRef.from_dict(plan["object_refs"][0])
        row = store.get_revision(plan_ref)
        decision = capture.command(human, "decision.record", {"subject_kind": "restore_plan",
            "subject_ref": plan_ref.to_dict(), "subject_digest": row["digest"], "action": "restore.apply",
            "target_scope": "project", "target_ref": row["payload"]["target_ref"], "decision": "approved",
            "reason": "test user approves exact fenced target"}, "decision", entry="human")
        payload = {"restore_plan_ref": plan_ref.to_dict(), "human_decision_ref": decision["object_refs"][0]}
        later = capture.command(server, "task.create", {"title": "post-backup-history", "goal": "preserve later history",
            "requirement_refs": [], "mode": "test"}, "later-task")["object_refs"][0]
        scope = context(store, "offline").scope
        with pytest.raises(KernelError) as busy:
            recovery.apply(scope, payload, "maintenance")
        assert busy.value.error.code == "TEMPORARY_UNAVAILABLE"
        refused = capture.command(server, "restore.apply", payload, "rpc-refusal", allow_rejected=True)
        assert refused["status"] == "rejected" and refused["error"]["code"] == "CAPABILITY_UNAVAILABLE"
        capture.data["observations"].update(wal_committed_not_in_main_file=True, backup_ref=backup_ref,
            backup_manifest=manifest, original_task=original, later_task=later, busy_error=busy.value.error.to_dict())
        capture.save(store)
        store.close()
        restored = recovery.apply(scope, payload, "maintenance")
        assert restored["status"] == "succeeded" and restored["writer_fence_held"]
        assert recovery.apply(scope, payload, "maintenance") == restored
        store = make_store(tmp_path)
        assert store.get_revision(ObjectRef.from_dict(original))
        assert store.get_revision(ObjectRef.from_dict(later)) is None
        historical = Store.open_project(Path(restored["history_backup"]["backup_path"]), "proj-a", "store-a", read_only=True)
        try:
            assert historical.get_revision(ObjectRef.from_dict(later))
        finally:
            historical.close()
        assert Path(restored["original_path"]).is_file()
        assert (Path(restored["audit_path"]) / "intent.json").is_file()
        capture.data["observations"]["offline_recovery"] = restored
    finally:
        capture.save(store)
        store.close()


def test_ac29_rpc_isolated_restore_target_authorization_and_busy_unknown(tmp_path, request):
    capture = Capture(tmp_path, request.node.nodeid)
    store = make_store(tmp_path)
    target = IsolatedRestoreTarget(tmp_path / "restored-copy", "test-copy")
    server = build_test_server(store, artifact_root=tmp_path / "artifacts", evidence_config={
        "backup_root": tmp_path / "backups", "restore_target": target})
    human = build_test_server(store, human=True)
    try:
        original = capture.command(server, "task.create", {"title": "backup-content", "goal": "verify restored copy",
            "requirement_refs": [], "mode": "test"}, "original-task")["object_refs"][0]
        store_ref = capture.host_seed(store, "store", "store-a", {"store_id": "store-a"})
        policy = capture.host_seed(store, "policy", "backup", {"mode": "test"})
        backup = capture.command(server, "backup.create", {"store_ref": store_ref.to_dict(),
            "policy_ref": policy.to_dict()}, "backup")
        backup_state = capture.query(server, "operation.status", {"operation_id": backup["operation_id"]})["data"]
        backup_ref = backup_state["result_refs"][0]
        plan = capture.command(server, "restore.plan", {"revision_or_backup_ref": backup_ref,
            "restore_kind": "disaster_recovery", "reason": "isolated offline copy only"}, "plan")
        plan_ref = ObjectRef.from_dict(plan["object_refs"][0])
        row = store.get_revision(plan_ref)
        wrong_target = capture.host_seed(store, "restore_target", "wrong", {"target_id": "other", "target_scope": "project"})
        decision_payload = {"subject_kind": "restore_plan", "subject_ref": plan_ref.to_dict(),
            "subject_digest": row["digest"], "action": "restore.apply", "target_scope": "project",
            "target_ref": wrong_target.to_dict(), "decision": "approved", "reason": "synthetic wrong target counterexample"}
        wrong_decision = capture.command(human, "decision.record", decision_payload, "wrong-decision", entry="human")
        denied = capture.raw(server, "restore.apply", {"restore_plan_ref": plan_ref.to_dict(),
            "human_decision_ref": wrong_decision["object_refs"][0]}, "wrong-target")
        assert denied["error"]["data"]["code"] == "PERMISSION_DENIED"
        assert not target.root.exists()
        decision = capture.command(human, "decision.record", {**decision_payload,
            "target_ref": row["payload"]["target_ref"], "reason": "test user approves pinned copy destination"},
            "correct-decision", entry="human")
        payload = {"restore_plan_ref": plan_ref.to_dict(), "human_decision_ref": decision["object_refs"][0]}
        later = capture.command(server, "task.create", {"title": "live-later-history", "goal": "live store preserved",
            "requirement_refs": [], "mode": "test"}, "later-task")["object_refs"][0]
        restored = capture.command(server, "restore.apply", payload, "restore-copy")
        observed = capture.query(server, "operation.status", {"operation_id": restored["operation_id"]})["data"]
        assert observed["status"] == "succeeded" and observed["writer_fence_held"]
        assert observed["mode"] == "isolated_offline_copy" and observed["original_store_preserved"]
        destination = Path(observed["restored_path"])
        assert destination.is_relative_to(target.root.resolve())
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == observed["file_sha256"]
        copied = Store.open_project(destination, "proj-a", "store-a", read_only=True)
        try:
            assert copied.get_revision(ObjectRef.from_dict(original))
            assert copied.get_revision(ObjectRef.from_dict(later)) is None
            assert copied.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert copied.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            copied.close()
        assert store.get_revision(ObjectRef.from_dict(later))
        before = destination.read_bytes()
        assert capture.command(server, "restore.apply", payload, "restore-copy") == restored
        assert destination.read_bytes() == before
        with target.fence():
            busy = capture.command(server, "restore.apply", payload, "busy-restore")
            unknown = capture.query(server, "operation.status", {"operation_id": busy["operation_id"]})["data"]
            assert unknown["status"] == "unknown" and unknown["error"]["type"] == "FileExistsError"
        assert capture.command(server, "restore.apply", payload, "busy-restore") == busy
        assert not (target.root / (busy["operation_id"] + ".sqlite")).exists()
        capture.data["observations"].update(restored=observed, busy_unknown=unknown,
            wrong_target_response=denied, live_history_preserved=later, restore_hash=observed["file_sha256"])
    finally:
        capture.save(store)
        store.close()


def test_ac30_rpc_coverage_and_typed_multihop_graph(tmp_path, request):
    capture = Capture(tmp_path, request.node.nodeid)
    store = make_store(tmp_path)
    server = build_test_server(store, environment_provider=PythonEnvironmentProbe())
    try:
        document = capture.host_seed(store, "source_document", "document", {"text": "synthetic requirement source"})
        def invoke(name, body, key):
            if name == "requirement.save":
                body = {**body, "source_refs": [document.to_dict()]}
            if name == "rules.save":
                body = {**body, "ruleset_id": "req-1"}
            return capture.command(server, name, body, key)
        prepared = prepare_dispatch(store, tmp_path, invoke=invoke)
        draft = capture.command(server, "requirement.save", {"object_id": "zero-links", "title": "unlinked requirement",
            "source_text": "no packet yet", "assumptions": [], "negative_requirements": [], "source_refs": []}, "unlinked")["object_refs"][0]
        capture.command(server, "requirement.confirm", {"draft_ref": draft, "acceptance_items": [{
            **prepared["item"], "item_id": "zero-link-item", "requirement_ref": draft}],
            "confirmed_assumptions": []}, "unlinked-confirm")
        coverage = capture.query(server, "requirements.coverage")
        assert coverage["data"]["denominator"] == 2
        assert coverage["data"]["covered"] == 1
        assert coverage["data"]["not_applicable_ids"] == ["zero-links"]
        assert coverage["data"]["uncovered"] == ["zero-links"]
        graph = capture.query(server, "project.trace", {"root_ref": prepared["packet"].to_dict(),
            "direction": "outgoing", "max_depth": 2})
        assert graph["data"]["nodes"] and graph["data"]["edges"]
        types = {item["object_type"] for item in graph["data"]["nodes"] if item["object_id"] == "req-1"}
        assert types == {"requirement", "rules", "acceptance"}
        assert any(item["object_type"] == "source_document" and item["depth"] == 2 for item in graph["data"]["nodes"])
        incoming = capture.query(server, "project.trace", {"root_ref": prepared["requirement"].to_dict(),
            "direction": "incoming", "max_depth": 1})
        assert any(item["object_id"] == prepared["packet"].object_id for item in incoming["data"]["nodes"])
        cut = capture.query(server, "project.trace", {"root_ref": prepared["packet"].to_dict(),
            "direction": "outgoing", "max_depth": 1})
        assert cut["data"]["truncated"] and cut["completeness"] == "incomplete"
        missing = capture.raw(server, "project.trace", {"root_ref": {**prepared["task"].to_dict(), "object_id": "absent"},
            "direction": "both", "max_depth": 1}, query=True)
        assert missing["error"]["data"]["code"] == "REFERENCE_NOT_FOUND"
        capture.data["observations"].update(coverage=coverage, graph=graph, incoming=incoming, cutoff=cut)
    finally:
        capture.save(store)
        store.close()


def test_ac31_rpc_watermarks_unknown_usage_and_read_model_rebuild(tmp_path, request):
    capture = Capture(tmp_path, request.node.nodeid)
    store = make_store(tmp_path)
    executor = RecordedExecutor()
    server = build_test_server(store, executor=executor, artifact_root=tmp_path / "artifacts",
                              environment_provider=PythonEnvironmentProbe())
    try:
        first = capture.command(server, "task.create", {"title": "first", "goal": "historical read",
            "requirement_refs": [], "mode": "test"}, "first")
        watermark = capture.query(server, "project.overview")["as_of_seq"]
        capture.command(server, "task.create", {"title": "later", "goal": "advance head",
            "requirement_refs": [], "mode": "test"}, "later")
        historical = capture.query(server, "project.overview", as_of_seq=watermark)
        timeline = capture.query(server, "project.timeline", as_of_seq=watermark)
        events = capture.query(server, "events.read", {"after": {"commit_seq": "0", "event_index": 0}, "limit": 100},
                               as_of_seq=watermark)
        assert historical["as_of_seq"] == timeline["as_of_seq"] == events["as_of_seq"] == watermark
        assert historical["data"]["object_counts"]["task"] == 1
        assert historical["freshness"]["projection_stale"] and historical["freshness"]["projection_lag_seq"] != "0"
        assert historical["completeness"] == "incomplete"
        assert all(int(item["commit_seq"]) <= int(watermark) for item in timeline["data"]["events"])
        future = capture.raw(server, "project.overview", {}, query=True, as_of_seq=str(store.next_commit_seq() + 100))
        assert future["error"]["data"]["code"] == "AS_OF_UNAVAILABLE"
        prepared = prepare_dispatch(store, tmp_path, invoke=lambda name, body, key:
            capture.command(server, name, body, "usage-" + key))
        capture.command(server, "attempt.start", {"packet_ref": prepared["packet"].to_dict(), "strategy_id": "s1",
            "execution_root_ref": prepared["roots"]["s1"].to_dict()}, "unknown-usage")
        comparison = capture.query(server, "attempts.compare", {"task_ref": prepared["task"].to_dict()})
        cost = comparison["data"]["cost"]
        assert cost["unknown"] and cost["total"] is None
        assert cost["missing_usage_is_not_zero"] is True and cost["completeness"] == "incomplete"
        as_of = comparison["as_of_seq"]
        before = capture.query(server, "project.overview", as_of_seq=as_of)
        query_service = QueryService(store)
        count_before = store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0]
        rebuilt = query_service.rebuild_read_model(as_of_seq=as_of)
        rebuilt_again = query_service.rebuild_read_model(as_of_seq=as_of)
        assert rebuilt["data"]["consistent"] and rebuilt["data"]["persisted"] is False
        assert rebuilt["data"]["digest"] == rebuilt_again["data"]["digest"]
        assert store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0] == count_before
        after = capture.query(server, "project.overview", as_of_seq=as_of)
        assert before["data"] == after["data"]
        assert rebuilt["data"]["rebuilt"]["project.overview"]["object_counts"] == before["data"]["object_counts"]
        capture.data["observations"].update(first=first, watermark=watermark, historical=historical,
            timeline=timeline, events=events, comparison=comparison, rebuild=rebuilt, before=before, after=after,
            rebuild_limit="read-only application read API; no frozen projection.rebuild RPC or durable checkpoint")
    finally:
        capture.save(store)
        store.close()


def test_ac32_rpc_immutable_synthetic_migration_and_replay(tmp_path, request):
    capture = Capture(tmp_path, request.node.nodeid)
    store = make_store(tmp_path)
    try:
        source_root = make_legacy_source(tmp_path)
        source_path = source_root / "legacy.sqlite"
        source_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
        manifest = build_source_manifest(source_root, "synthetic-source")
        records = LegacyReader(source_root, "synthetic-source").read()
        digest = snapshot_digest("synthetic-source", manifest, records)
        snapshot_ref = capture.host_seed(store, "legacy_source_snapshot", "snapshot", {
            "source_store_id": "synthetic-source", "manifest_digest": manifest.digest, "snapshot_digest": digest})
        snapshot = LegacySnapshot(snapshot_ref, digest, "synthetic-source", records, manifest, "user-1")
        class Provider:
            calls = 0
            def read_snapshot(self, ref):
                assert ref == snapshot_ref
                self.calls += 1
                return snapshot
        provider = Provider()
        server = build_test_server(store, legacy_config={"snapshot_provider": provider,
            "trusted_snapshot_producers": {"user-1": ["synthetic-source"]}})
        plan_ref = capture.host_seed(store, "legacy_import_plan", "plan", {
            "source_snapshot_ref": snapshot_ref.to_dict(), "target_project_id": "proj-a", "target_store_id": "store-a",
            "source_store_id": "synthetic-source", "project_mapping": {"p-a": "proj-a"},
            "manifest_digest": manifest.digest, "batch_id": "g2-ac32"})
        payload = {"source_snapshot_ref": snapshot_ref.to_dict(), "import_plan_ref": plan_ref.to_dict()}
        first = capture.command(server, "legacy.import", payload, "import")
        revisions_before = store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0]
        replay = capture.command(server, "legacy.import", payload, "import")
        assert replay == first and provider.calls == 1
        rerun = capture.command(server, "legacy.import", payload, "import-another-key")
        assert store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == revisions_before
        assert rerun["object_refs"][-1] == first["object_refs"][-1]
        report = store.get_revision(ObjectRef.from_dict(first["object_refs"][-1]))["payload"]
        facts = QueryService(store).latest_revisions("imported_fact")
        quarantined = QueryService(store).latest_revisions("legacy_quarantine")
        assert any(item["payload"]["classification"] == "orphan" for item in quarantined)
        assert any(item["payload"]["classification"] == "unowned" for item in quarantined)
        assert report["quarantined"] == len(quarantined)
        assert facts and all("raw" in item["payload"] for item in facts)
        for item in facts:
            body = item["payload"]
            assert "passed" not in body and "approved" not in body and "cost" not in body
            assert body["source_digest"] == sha256_digest(body["raw"])
        assert not QueryService(store).latest_revisions("verification")
        assert not QueryService(store).latest_revisions("approval")
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_before
        timeline = capture.query(server, "project.timeline")
        disabled = build_test_server(store)
        denied = capture.raw(disabled, "legacy.import", payload, "disabled")
        assert denied["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
        changed = {"source_snapshot_ref": snapshot_ref.to_dict(), "import_plan_ref": {**plan_ref.to_dict(), "revision_id": "absent"}}
        mismatch = capture.raw(server, "legacy.import", changed, "mismatch")
        assert mismatch["error"]["data"]["code"] == "REFERENCE_NOT_FOUND"
        capture.data["observations"].update(source_sha256_before=source_before,
            source_sha256_after=hashlib.sha256(source_path.read_bytes()).hexdigest(), source_manifest=manifest.to_dict(),
            snapshot_digest=digest, imported_facts=facts, quarantine=quarantined, import_report=report,
            first_receipt=first, replay_receipt=replay, rerun_receipt=rerun, timeline=timeline,
            native_verification_count=0, native_approval_count=0, source_read_mode="SQLite mode=ro with PRAGMA query_only=ON")
    finally:
        capture.save(store)
        store.close()
