"""Recoverable project binding across project and identity SQLite stores."""
from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from ..contracts import sha256_digest
from ..contracts.dto import CommandContext, ObjectRef
from ..contracts.errors import KernelError, invalid_input, scope_mismatch
from ..data.store.uow import UnitOfWork
from .design.references import checked_payload
from .security import require_scope


class ProjectBindingService:
    def __init__(self, store, identity_registry):
        self.store = store
        self.registry = identity_registry

    def project_bind(self, ctx: CommandContext, payload: Mapping[str, Any]):
        require_scope(self.store, ctx.scope, "project.admin")
        data = checked_payload("project.bind", payload)
        if data["project_id"] != ctx.scope.project_id or data["project_id"] != self.store.project_id:
            raise KernelError(scope_mismatch("binding project differs from the authorized project"))
        if ctx.scope.store_id != self.store.store_id:
            raise KernelError(scope_mismatch("authorized store differs from project store"))
        meta = self.store.get_project_meta()
        if meta is None or meta["store_id"] != self.store.store_id:
            raise KernelError(scope_mismatch("project store stamp is missing or inconsistent"))
        identity_project = self.registry.conn.execute(
            "SELECT state,store_id FROM identity_project WHERE project_id=?",
            (data["project_id"],)).fetchone()
        if identity_project is None or identity_project[0] != "active":
            raise KernelError(scope_mismatch("identity project is not active"))
        if identity_project[1] != self.store.store_id:
            raise KernelError(scope_mismatch("identity and project store stamps differ"))

        operation_id = "project-bind-" + sha256_digest({
            "project_id": data["project_id"], "principal_id": ctx.scope.principal_id,
            "idempotency_key": ctx.idempotency_key})[:32]

        def claim(handles):
            head = self.store.get_head("project_binding_operation", operation_id, "current")
            if head is None:
                ref = handles.records.append_revision("project_binding_operation", operation_id,
                    {"operation_id": operation_id, "status": "pending",
                     "project_id": data["project_id"], "binding": data,
                     "input_hash": ctx.input_hash, "principal_id": ctx.scope.principal_id},
                    "project/binding-operation")
                handles.records.publish_head(ref, "current", expected_head_version=None)
            else:
                ref = ObjectRef(self.store.project_id, "project_binding_operation",
                                operation_id, head["revision_id"])
                saved = self.store.get_revision(ref)["payload"]
                if saved.get("input_hash") != ctx.input_hash or saved.get("binding") != data:
                    raise KernelError(invalid_input("binding operation claim differs from its persisted input"))
            handles.outcome.object_refs = (ref,)
            handles.outcome.operation_id = operation_id

        claim_receipt = UnitOfWork(self.store, ctx, "project.bind").execute(claim)
        if claim_receipt.status != "accepted":
            return claim_receipt
        current, head = self._operation(operation_id)
        if current["status"] in {"completed", "failed"}:
            return claim_receipt

        try:
            registry_result = self._registry_bind_once(ctx, operation_id, data)
        except KernelError as exc:
            if exc.error.retryable or exc.error.category == "unknown":
                return claim_receipt
            self._settle(ctx, operation_id, "failed", error=exc.error.to_dict())
            return claim_receipt

        self._settle(ctx, operation_id, "completed", result=registry_result)
        return claim_receipt

    def _operation(self, operation_id: str):
        head = self.store.get_head("project_binding_operation", operation_id, "current")
        if head is None:
            raise KernelError(scope_mismatch("project binding operation claim is missing"))
        ref = ObjectRef(self.store.project_id, "project_binding_operation", operation_id,
                        head["revision_id"])
        return self.store.get_revision(ref)["payload"], head

    def _registry_bind_once(self, ctx, operation_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        ledger = self.registry.command_ledger
        conn = self.registry.conn
        internal_key = self._identity_key(ctx, operation_id)
        prior = ledger.lookup(ctx.scope.principal_id, internal_key)
        if prior is not None:
            if (prior["command_kind"] != "project.bind"
                    or prior["input_hash"] != ctx.input_hash):
                raise KernelError(invalid_input("identity idempotency key conflicts with another binding"))
            if prior["result"] is None:
                raise RuntimeError("identity binding result is missing; reconcile the registry ledger")
            return prior["result"]

        conn.execute("BEGIN IMMEDIATE")
        try:
            prior = ledger.lookup(ctx.scope.principal_id, internal_key)
            if prior is not None:
                if (prior["command_kind"] != "project.bind"
                        or prior["input_hash"] != ctx.input_hash):
                    raise KernelError(invalid_input("identity idempotency key conflicts with another binding"))
                result = prior["result"]
                if result is None:
                    raise RuntimeError("identity binding result is missing; reconcile the registry ledger")
                conn.execute("COMMIT")
                return result

            result = self.registry.bind(data["project_id"], data["host_id"],
                data["binding_kind"], data["canonical_key"], data["expected_binding_version"])
            seq = ledger.next_commit_seq()
            command_id = "cmd-" + uuid.uuid4().hex
            conn.execute(
                "INSERT INTO identity_command_receipt (principal_id,idempotency_key,command_kind,"
                "input_hash,command_id,status,request_id,commit_seq,receipt_json,result_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ctx.scope.principal_id, internal_key, "project.bind", ctx.input_hash,
                 command_id, "committed", operation_id, seq,
                 None, json.dumps(result, ensure_ascii=False)))
            ledger.save_commit_seq(seq)
            conn.execute("COMMIT")
            return result
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    @staticmethod
    def _identity_key(ctx, operation_id: str) -> str:
        return "project.bind:" + ctx.scope.project_id + ":" + operation_id

    def _settle(self, ctx, operation_id: str, status: str, *, result=None, error=None):
        settle_token = sha256_digest({"project_id": ctx.scope.project_id,
            "principal_id": ctx.scope.principal_id, "idempotency_key": ctx.idempotency_key,
            "operation_id": operation_id})[:40]
        settle_ctx = CommandContext(scope=ctx.scope, command_id="cmd-pbind-" + settle_token,
            idempotency_key="pb-settle-" + settle_token,
            input_hash=sha256_digest({"operation_id": operation_id, "status": status,
                                     "result": result, "error": error}),
            expected_heads=(), source=ctx.source)

        def cb(handles):
            prior, head = self._operation(operation_id)
            if prior["status"] in {"completed", "failed"}:
                return
            updated = {**prior, "status": status, "registry_result": result,
                       "error": error, "settled_seq": handles.records.commit_seq}
            ref = handles.records.append_revision("project_binding_operation", operation_id,
                updated, "project/binding-operation",
                parent_ref=ObjectRef(self.store.project_id, "project_binding_operation",
                                     operation_id, head["revision_id"]))
            handles.records.publish_head(ref, "current", str(head["head_version"]))
            handles.audit("project.binding_settled", {"operation_id": operation_id,
                "status": status, "registry_result": result, "error": error},
                object_refs=[ref.to_dict()])
            handles.outcome.object_refs = (ref,)

        return UnitOfWork(self.store, settle_ctx, "project.bind.settle").execute(cb)
