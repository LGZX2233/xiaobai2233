"""Trusted RPC entry for identity-owned project lifecycle commands."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...contracts.errors import (KernelError, as_of_unavailable, idempotency_conflict,
                                 invalid_input, permission_denied)
from ...data.identity.registry import IdentityRegistry
from ...interfaces.rpc.commands import compute_input_hash
from .invocation import InvocationContextRegistry, current_machine_context
from .protocol import ProtocolServer

IDENTITY_COMMANDS = ("project.provision", "project.reconcile")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _receipt(*, command: str, key: str, command_id: str, commit_seq: int,
             store_id: str) -> dict[str, Any]:
    return {"command_id": command_id, "idempotency_key": key, "command": command,
            "status": "committed", "commit_seq": str(commit_seq),
            "event_cursor": {"commit_seq": str(commit_seq), "event_index": 0},
            "object_refs": [], "result_refs": [], "receipt_domain": "identity",
            "store_id": store_id, "committed_at": _utc_now()}


def build_identity_server(data_root: Path | str, *, contexts: InvocationContextRegistry,
                          principal: str = "identity-owner",
                          capabilities: frozenset[str] = frozenset({"project.admin"}),
                          mode: str = "production") -> ProtocolServer:
    """Build the separate identity command surface backed by shared.sqlite."""
    if contexts is None:
        raise ValueError("a trusted InvocationContextRegistry is required")
    registry = IdentityRegistry(Path(data_root))

    def command_handler(command: str, params: dict[str, Any]) -> dict[str, Any]:
        context = current_machine_context()
        if context is None or "project.admin" not in context.capabilities:
            raise KernelError(permission_denied("project.admin is required for identity commands"))
        selector = params["selector"]
        project_id = selector["project_id"]
        payload = params["payload"]
        key = params["idempotency_key"]
        input_hash = compute_input_hash(command, selector, params.get("expected_heads"), payload)
        command_id = "cmd-" + uuid.uuid4().hex[:24]
        request_id = None
        conn = registry.conn

        if context.project_id != project_id:
            raise KernelError(permission_denied("identity selector differs from trusted project"))
        if command == "project.reconcile" and registry.project_for_provision_request(
                payload["provision_request_id"]) != project_id:
            raise KernelError(permission_denied(
                "provision request does not belong to selected project"))

        try:
            conn.execute("BEGIN IMMEDIATE")
            previous = registry.command_ledger.lookup(context.principal_id, key)
            if previous is not None:
                if previous["command_kind"] != command or previous["input_hash"] != input_hash:
                    raise KernelError(idempotency_conflict(
                        f"identity idempotency key {key!r} was used with different content"))
                if previous["receipt"] is not None:
                    conn.execute("COMMIT")
                    return {"receipt": previous["receipt"], "data": previous["result"]}
                request_id = previous["request_id"]
                command_id = previous["command_id"]
                conn.execute("COMMIT")
            else:
                if command == "project.provision" and registry.project_state(project_id) is not None:
                    raise KernelError(permission_denied(
                        "project already exists; use its original provision request"))
                request_id = "pr-" + uuid.uuid4().hex if command == "project.provision" else None
                commit_seq = registry.command_ledger.next_commit_seq()
                conn.execute(
                    "INSERT INTO identity_command_receipt "
                    "(principal_id,idempotency_key,command_kind,input_hash,command_id,status,request_id) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (context.principal_id, key, command, input_hash, command_id, "pending", request_id))
                if command == "project.provision":
                    registry.begin_provision(context.principal_id, project_id,
                        payload["display_name"], payload["canonical_root"], request_id)
                registry.command_ledger.save_commit_seq(commit_seq)
                conn.execute("COMMIT")
            if conn.in_transaction:
                conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

        try:
            if command == "project.provision":
                data = registry.reconcile(request_id)
                conn.execute("BEGIN IMMEDIATE")
                bindings = [registry.bind(project_id, payload["host_id"], "root",
                                          payload["canonical_root"], "0")]
                if payload.get("workspace_id"):
                    bindings.append(registry.bind(project_id, payload["host_id"], "workspace",
                                                  payload["workspace_id"], "0"))
                data = {**data, "bindings": bindings}
            elif command == "project.reconcile":
                conn.execute("BEGIN IMMEDIATE")
                data = registry.reconcile(payload["provision_request_id"])
            else:
                raise ValueError(f"unsupported identity command {command}")

            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            committed = registry.command_ledger.lookup(context.principal_id, key)
            if committed is not None and committed["receipt"] is not None:
                conn.execute("COMMIT")
                return {"receipt": committed["receipt"], "data": committed["result"]}
            commit_seq = registry.command_ledger.next_commit_seq()
            receipt = _receipt(command=command, key=key, command_id=command_id,
                               commit_seq=commit_seq, store_id=registry.store_id)
            conn.execute(
                "UPDATE identity_command_receipt SET status='committed',commit_seq=?,receipt_json=?,"
                "result_json=? WHERE principal_id=? AND idempotency_key=?",
                (commit_seq, json.dumps(receipt, ensure_ascii=False),
                 json.dumps(data, ensure_ascii=False), context.principal_id, key))
            registry.command_ledger.save_commit_seq(commit_seq)
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return {"receipt": receipt, "data": data}

    def query_handler(query: str, params: dict[str, Any]) -> dict[str, Any]:
        context = current_machine_context()
        if context is None or "project.admin" not in context.capabilities:
            raise KernelError(permission_denied("project.admin is required for identity receipts"))
        if context.project_id != params["selector"]["project_id"]:
            raise KernelError(permission_denied("identity receipt selector differs from trusted project"))
        if params["payload"]["receipt_domain"] != "identity":
            raise KernelError(invalid_input("identity server only serves identity receipts"))
        row_entry = registry.command_ledger.lookup(
            context.principal_id, params["payload"]["idempotency_key"])
        entry = (row_entry if row_entry is not None and row_entry["receipt"] is not None
                 and (row_entry["result"] or {}).get("project_id") == params["selector"]["project_id"]
                 else None)
        row = registry.conn.execute(
            "SELECT commit_seq FROM identity_meta WHERE store_id=?", (registry.store_id,)).fetchone()
        current_seq = int(row[0] if row else 0)
        requested = params.get("as_of_seq")
        as_of = current_seq if requested is None else int(requested)
        if as_of > current_seq:
            raise KernelError(as_of_unavailable())
        data = (None if entry is None or int(entry["commit_seq"]) > as_of
                else entry["receipt"])
        return {"as_of_seq": str(as_of), "projection_version": "identity.v1",
                "computed_at": _utc_now(), "source_watermarks": {}, "freshness": "current",
                "completeness": "complete", "gaps": [], "data": data}

    server = ProtocolServer(
        mode=mode, supported_commands=list(IDENTITY_COMMANDS), supported_queries=["command.receipt"],
        allowlist=frozenset(IDENTITY_COMMANDS), human_only_commands=frozenset(),
        context_resolver=contexts.resolve,
        command_handlers={name: command_handler for name in IDENTITY_COMMANDS},
        query_handler=query_handler)
    server.identity_registry = registry
    return server
