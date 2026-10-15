"""Project binding entry uses durable claims across separate SQLite stores."""
from __future__ import annotations

import pytest

from project_kernel.application.project_service import ProjectBindingService
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import CommandContext, ObjectRef, ResolvedScope
from project_kernel.contracts.errors import KernelError, invalid_input
from project_kernel.data.identity.registry import IdentityRegistry
from project_kernel.data.store.store import Store
from project_kernel.data.queries.service import QueryService
from project_kernel.data.store.uow import UnitOfWork


def _setup(tmp_path):
    registry = IdentityRegistry(tmp_path / "identity")
    provisioned = registry.provision("operator", "proj-a", "Project A",
        str(tmp_path / "canonical-a"), "host-a", "workspace-a", request_id="provision-a")
    store_path = registry._project_dir("proj-a") / "project.sqlite"
    store = Store.open_project(store_path, "proj-a", provisioned["store_id"])
    return registry, store


def _payload(**overrides):
    return {"project_id": "proj-a", "host_id": "host-a", "binding_kind": "workspace",
            "canonical_key": "workspace-a", "expected_binding_version": "1", **overrides}


def _ctx(store, key="bind-1", payload=None, *, capabilities=frozenset({"project.admin"}),
         project_id=None, store_id=None):
    scope = ResolvedScope(project_id or store.project_id, store_id or store.store_id,
                          "operator", capabilities, "test")
    return CommandContext(scope, "cmd", key,
        sha256_digest(payload if payload is not None else {"idempotency_key": key}))


def _operation(store, operation_id):
    head = store.get_head("project_binding_operation", operation_id, "current")
    return store.get_revision(ObjectRef(store.project_id, "project_binding_operation",
        operation_id, head["revision_id"]))["payload"]


def test_bind_recovers_after_registry_commit_before_project_settlement(tmp_path, monkeypatch):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        payload = _payload()
        ctx = _ctx(store, payload=payload)
        original_settle = service._settle
        settled = False
        def fail_once(*args, **kwargs):
            nonlocal settled
            if not settled:
                settled = True
                raise OSError("simulated process loss after registry commit")
            return original_settle(*args, **kwargs)
        monkeypatch.setattr(service, "_settle", fail_once)
        with pytest.raises(OSError):
            service.project_bind(ctx, payload)
        claim = store.get_receipt("operator", "bind-1")["receipt"]
        operation_id = claim["operation_id"]
        assert _operation(store, operation_id)["status"] == "pending"
        identity_row = registry.conn.execute(
            "SELECT project_id,binding_version FROM identity_binding WHERE host_id=? AND binding_kind=? AND canonical_key=?",
            ("host-a", "workspace", "workspace-a")).fetchone()
        assert identity_row == ("proj-a", "1")

        database = store.conn.execute("PRAGMA database_list").fetchone()[2]
        store.close()
        store_id = registry.conn.execute("SELECT store_id FROM identity_project WHERE project_id='proj-a'").fetchone()[0]
        reopened = Store.open_project(database, "proj-a", store_id)
        try:
            restarted = ProjectBindingService(reopened, registry)
            replay = restarted.project_bind(ctx, payload)
            assert replay.to_dict() == claim
            operation = _operation(reopened, operation_id)
            assert operation["status"] == "completed"
            assert operation["registry_result"]["unchanged"] is False
            ledger_key = restarted._identity_key(ctx, operation_id)
            ledger = registry.command_ledger.lookup("operator", ledger_key)
            assert ledger["command_kind"] == "project.bind"
            assert ledger["result"] == operation["registry_result"]
            assert ledger["receipt"] is None
            assert QueryService(reopened).operation_status(operation_id)["status"] == "completed"
            assert restarted.project_bind(ctx, payload).to_dict() == claim
        finally:
            reopened.close()
    finally:
        registry.close()


def test_bind_requires_admin_matching_project_and_matching_store_stamps(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        payload = _payload()
        for ctx in (
            _ctx(store, "no-admin", payload, capabilities=frozenset()),
            _ctx(store, "other-project", payload, project_id="proj-b"),
            _ctx(store, "other-store", payload, store_id="store-other"),
        ):
            with pytest.raises(KernelError):
                service.project_bind(ctx, payload)
        assert registry.conn.execute("SELECT COUNT(*) FROM identity_binding").fetchone()[0] == 0
        assert store.conn.execute("SELECT COUNT(*) FROM entity WHERE type='project_binding_operation'").fetchone()[0] == 0
    finally:
        store.close()
        registry.close()


def test_bind_idempotency_hash_conflict_has_no_second_registry_effect(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        first_payload = _payload()
        first = service.project_bind(_ctx(store, "bind-1", first_payload), first_payload)
        changed = _payload(canonical_key="workspace-other")
        with pytest.raises(KernelError):
            service.project_bind(_ctx(store, "bind-1", changed), changed)
        assert service.project_bind(_ctx(store, "bind-1", first_payload), first_payload) == first
        assert registry.conn.execute("SELECT COUNT(*) FROM identity_binding").fetchone()[0] == 1
        assert store.conn.execute("SELECT COUNT(*) FROM entity WHERE type='project_binding_operation'").fetchone()[0] == 1
    finally:
        store.close()
        registry.close()


def test_max_length_public_key_does_not_overflow_internal_settlement_key(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        payload = _payload()
        public_key = "k" * 128
        ctx = _ctx(store, public_key, payload)
        receipt = service.project_bind(ctx, payload)
        assert receipt.status == "accepted"
        assert _operation(store, receipt.operation_id)["status"] == "completed"
        settlement = store.conn.execute(
            "SELECT idempotency_key,command_id FROM command_receipt"
            " WHERE idempotency_key LIKE 'pb-settle-%'").fetchone()
        assert settlement is not None
        assert len(settlement[0]) <= 64
        assert len(settlement[1]) <= 64
    finally:
        store.close()
        registry.close()


def test_registry_version_conflict_is_settled_failed_without_binding_effect(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        registry.bind("proj-a", "host-a", "workspace", "workspace-a", "1")
        service = ProjectBindingService(store, registry)
        payload = _payload(expected_binding_version="2")
        receipt = service.project_bind(_ctx(store, "stale-bind", payload), payload)
        operation = _operation(store, receipt.operation_id)
        assert receipt.status == "accepted"
        assert operation["status"] == "failed"
        assert operation["error"]["code"] == "SCOPE_MISMATCH"
        assert registry.command_ledger.lookup("operator", "stale-bind") is None
        assert registry.conn.execute("SELECT COUNT(*) FROM identity_binding").fetchone()[0] == 1
    finally:
        store.close()
        registry.close()


def test_rejected_project_claim_does_not_call_registry(tmp_path, monkeypatch):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        monkeypatch.setattr(registry, "bind", lambda *args: pytest.fail("registry effect ran"))
        payload = _payload()
        ctx = _ctx(store, payload=payload)
        rejected = UnitOfWork(store, ctx, "project.bind")._commit_rejection
        monkeypatch.setattr(UnitOfWork, "execute", lambda self, callback: rejected(
            # UnitOfWork rejection behavior is already covered independently.
            invalid_input("rejected claim"), ctx.scope.principal_id))
        receipt = service.project_bind(ctx, payload)
        assert receipt.status == "rejected"
        assert registry.conn.execute("SELECT COUNT(*) FROM identity_binding").fetchone()[0] == 0
    finally:
        store.close()
        registry.close()


def test_internal_identity_key_is_namespaced_by_project_operation(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        ctx = _ctx(store, "same-key", _payload())
        op_a = "project-bind-a"
        op_b = "project-bind-b"
        assert service._identity_key(ctx, op_a) != service._identity_key(ctx, op_b)
        assert service._identity_key(ctx, op_a) != "same-key"
    finally:
        store.close()
        registry.close()


def test_identity_internal_key_does_not_collide_across_projects(tmp_path):
    registry, store_a = _setup(tmp_path)
    provisioned_b = registry.provision("operator", "proj-b", "Project B",
        str(tmp_path / "canonical-b"), "host-b", "workspace-b", request_id="provision-b")
    store_b = Store.open_project(registry._project_dir("proj-b") / "project.sqlite",
                                 "proj-b", provisioned_b["store_id"])
    try:
        service_a = ProjectBindingService(store_a, registry)
        service_b = ProjectBindingService(store_b, registry)
        ctx_a = _ctx(store_a, "shared-key", _payload())
        ctx_b = _ctx(store_b, "shared-key", _payload(project_id="proj-b", host_id="host-b",
                         canonical_key="workspace-b"))
        key_a = service_a._identity_key(ctx_a, "operation-a")
        key_b = service_b._identity_key(ctx_b, "operation-b")
        assert key_a != key_b
        service_a._registry_bind_once(ctx_a, "operation-a", _payload())
        service_b._registry_bind_once(ctx_b, "operation-b", _payload(project_id="proj-b",
            host_id="host-b", canonical_key="workspace-b"))
        assert registry.command_ledger.lookup("operator", key_a)["input_hash"] == ctx_a.input_hash
        assert registry.command_ledger.lookup("operator", key_b)["input_hash"] == ctx_b.input_hash
    finally:
        store_a.close()
        store_b.close()
        registry.close()


def test_unknown_registry_commit_stays_pending_and_retry_recovers(tmp_path, monkeypatch):
    registry, store = _setup(tmp_path)
    try:
        service = ProjectBindingService(store, registry)
        payload = _payload()
        ctx = _ctx(store, payload=payload)
        original = registry.bind
        raised = False

        def commit_then_raise(*args, **kwargs):
            nonlocal raised
            result = original(*args, **kwargs)
            if not raised:
                raised = True
                raise RuntimeError("connection lost after registry commit")
            return result

        monkeypatch.setattr(registry, "bind", commit_then_raise)
        with pytest.raises(RuntimeError):
            service.project_bind(ctx, payload)
        claim = store.get_receipt("operator", "bind-1")["receipt"]
        operation_id = claim["operation_id"]
        assert _operation(store, operation_id)["status"] == "pending"
        assert QueryService(store).operation_status(operation_id)["status"] == "pending"
        replay = service.project_bind(ctx, payload)
        assert replay.to_dict() == claim
        assert _operation(store, operation_id)["status"] == "completed"
    finally:
        store.close()
        registry.close()
