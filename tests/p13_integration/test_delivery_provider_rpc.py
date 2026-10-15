"""Non-file delivery through project-bound RPC and verified human approval."""
from __future__ import annotations

from pathlib import Path
import sys
import hashlib

import pytest

from project_kernel.application.environment_service import PythonEnvironmentProbe
from project_kernel.bootstrap import KernelServices
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import ObjectRef, CheckResult, ArtifactRef
from project_kernel.data.store.store import Store
from project_kernel.evidence import ArtifactStorage, BundleExporter
from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame

from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, seed
from p03_attempt.fixture_executor import FixtureSubprocessExecutor
from p04_delivery.memory_provider import MemoryDeliveryProvider
from p13_integration.auth_helpers import build_test_server
from p13_integration.test_closed_loop import call, latest


class _ArtifactChecks:
    def __init__(self, store, storage):
        self.store = store
        self.storage = storage

    def run(self, scope, attempt, candidate, acceptance_refs):
        payload = self.store.get_revision(candidate)["payload"]
        assert self.storage.open_read(ArtifactRef(**payload["artifacts"][0])) == b"memory deliverable"
        acceptance_ref = (acceptance_refs[0] if isinstance(acceptance_refs[0], ObjectRef)
                          else ObjectRef.from_dict(acceptance_refs[0]))
        items = self.store.get_revision(acceptance_ref)["payload"]["acceptance_items"]
        return tuple(CheckResult(item["item_id"], ObjectRef.from_dict(item["recipe_ref"]),
                                 candidate_digest=payload["candidate_digest"], result="pass",
                                 evidence_mode="test") for item in items)


def _response(server, project, command, payload, key):
    return decode_frame(server.handle_line(encode_frame({
        "jsonrpc": "2.0", "id": key, "method": "kernel.command", "params": {
            "protocol_version": "1.0.0", "invocation_context_id": "ctx1",
            "selector": {"project_id": project}, "command": command,
            "payload": payload, "expected_heads": [], "idempotency_key": key}})))


def test_rpc_memory_delivery_approval_unknown_restart_recovery_and_close(tmp_path):
    store = make_store(tmp_path)
    storage = ArtifactStorage(tmp_path / "artifacts")
    provider = MemoryDeliveryProvider(storage)
    provider.observation_unavailable = True
    executor = FixtureSubprocessExecutor({"s1": [sys.executable, "-B", "-c", "print('complete')"]})
    server = build_test_server(store, delivery_provider=provider, artifact_root=tmp_path / "artifacts",
                               executor=executor, environment_provider=PythonEnvironmentProbe(),
                               check_provider=_ArtifactChecks(store, storage))
    human = build_test_server(store, human=True)
    invoke = lambda name, body, key: call(server, "proj-a", name, body, key)
    try:
        prepared = prepare_dispatch(store, tmp_path, invoke=invoke)
        started = invoke("attempt.start", {
            "packet_ref": prepared["packet"].to_dict(), "strategy_id": "s1",
            "execution_root_ref": prepared["roots"]["s1"].to_dict()}, "memory-attempt")
        attempt = latest(store, "attempt", started["operation_id"])
        artifact = storage.publish(storage.stage(b"memory deliverable", "text/plain"), "text/plain")
        candidate = seed(store, "candidate_manifest", "memory-candidate", {
            "attempt_ref": attempt.to_dict(),
            "candidate_digest": hashlib.sha256(b"memory deliverable").hexdigest(),
            "artifacts": [artifact.to_dict()]})
        invoke("verification.run", {"attempt_ref": attempt.to_dict(),
            "candidate_manifest_ref": candidate.to_dict(),
            "acceptance_refs": [prepared["acceptance"].to_dict()]}, "memory-verify")
        selection = invoke("attempt.select", {"attempt_ref": attempt.to_dict(),
            "comparison_refs": [attempt.to_dict()], "purpose": "delivery",
            "reason": "select verified isolated candidate"}, "memory-select")["object_refs"][0]
        target = seed(store, "delivery_target", "memory-target", provider.target())
        requested = invoke("delivery.request", {"selection_ref": selection,
            "candidate_ref": candidate.to_dict(), "target_ref": target.to_dict()}, "memory-request")
        approval = store.get_revision(ObjectRef.from_dict(requested["object_refs"][0]))["payload"]
        payload = {"approval_id": approval["approval_id"], "snapshot_digest": approval["snapshot_digest"]}
        unapproved = _response(server, "proj-a", "delivery.apply", payload, "unapproved")
        assert unapproved["result"]["receipt"]["error"]["code"] == "APPROVAL_INVALID"
        decide = {**payload, "decision": "approved", "reason": "human reviewed memory namespace"}
        machine_decide = _response(server, "proj-a", "approval.decide", decide, "machine-approve")
        assert machine_decide["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
        call(human, "proj-a", "approval.decide", decide, "memory-approve")
        foreign = _response(server, "proj-b", "delivery.apply", payload, "foreign-apply")
        assert foreign["error"]["data"]["code"] == "SCOPE_MISMATCH"
        assert not provider.apply_calls

        applied = invoke("delivery.apply", payload, "memory-apply")
        assert applied["status"] == "accepted"
        operation_id = applied["operation_id"]
        query = {"operation_id": operation_id}
        operation = call(server, "proj-a", "operation.status", query, query=True)["data"]
        assert operation["status"] == operation["effect_status"] == "unknown"
        assert operation["sink_receipt"]["sink_id"] == "memory"
        assert operation["sink_receipt"]["state"] == "succeeded"
        archived_receipt = call(server, "proj-a", "command.receipt", {
            "receipt_domain": "project", "idempotency_key": "memory-apply"}, query=True)["data"]
        assert archived_receipt["receipt"] == applied
        assert invoke("delivery.apply", payload, "memory-apply") == applied
        invoke("delivery.reconcile", query, "unavailable-reconcile")
        assert call(server, "proj-a", "operation.status", query, query=True)["data"]["status"] == "unknown"
        assert provider.apply_calls == [(operation_id, "memory")]

        path = Path(store.conn.execute("PRAGMA database_list").fetchone()[2])
        store.close()
        store = Store.open_project(path, "proj-a", "store-a")
        server = build_test_server(store, delivery_provider=provider, artifact_root=tmp_path / "artifacts")
        assert invoke("delivery.apply", payload, "memory-apply") == applied
        provider.observation_unavailable = False
        invoke("delivery.reconcile", query, "restored-reconcile")
        operation = call(server, "proj-a", "operation.status", query, query=True)["data"]
        assert operation["status"] == "applied"
        assert provider.published[operation_id]["manifest"]["required_sinks"] == ["memory"]
        assert provider.published[operation_id]["artifacts"] == {artifact.sha256: b"memory deliverable"}
        closed = invoke("task.close", {"task_ref": prepared["task"].to_dict(),
            "applied_operation_ref": latest(store, "delivery", operation_id).to_dict()}, "memory-close")
        task = store.get_revision(ObjectRef.from_dict(closed["object_refs"][0]))["payload"]
        assert task["phase"] == "closed" and task["terminal_outcome"] == "delivered"
        invoke("delivery.reconcile", query, "terminal-reconcile")
        assert provider.apply_calls == [(operation_id, "memory")]
    finally:
        store.close()


def test_composition_rejects_conflicting_delivery_provider_configuration(tmp_path):
    store = make_store(tmp_path)
    storage = ArtifactStorage(tmp_path / "artifacts")
    provider = MemoryDeliveryProvider(storage)
    exporter = BundleExporter(tmp_path / "exports", storage)
    try:
        with pytest.raises(ValueError, match="delivery_provider"):
            KernelServices(store, delivery_provider=provider, bundle_exporter=exporter)
        for human in (False, True):
            with pytest.raises(ValueError, match="delivery_provider"):
                build_test_server(store, human=human, delivery_provider=provider, bundle_exporter=exporter)
        services = KernelServices(store)
        assert services.delivery.provider is None
    finally:
        store.close()
