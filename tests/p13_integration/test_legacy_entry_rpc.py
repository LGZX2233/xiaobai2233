"""Configured synthetic import through the normal machine protocol entry."""
from dataclasses import replace
from pathlib import Path

import pytest

from project_kernel.bootstrap import build_server
from project_kernel.contracts.dto import ObjectRef
from project_kernel.data.store.store import Store
from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame
from project_kernel.interfaces.rpc.invocation import InvocationContextRegistry
from p07_migration.test_entry import _setup


def call(server, project_id, payload, *, key="rpc-import", handle="operator"):
    return decode_frame(server.handle_line(encode_frame({
        "jsonrpc": "2.0", "id": key, "method": "kernel.command", "params": {
            "protocol_version": "1.0.0", "invocation_context_id": handle,
            "selector": {"project_id": project_id}, "expected_heads": [],
            "idempotency_key": key, "command": "legacy.import", "payload": payload}})))


def server_for(store, provider, *, configured=True, mode="test"):
    contexts=InvocationContextRegistry(handle_factory=lambda: "operator")
    contexts.mint("operator", frozenset({"project.admin", "project.read"}), project_id=store.project_id)
    options = {"snapshot_provider": provider, "trusted_snapshot_producers": {"producer": ["source-a"]}}
    return build_server(store, principal="operator", contexts=contexts, mode=mode,
                        legacy_config=options if configured else None)


def test_configured_legacy_rpc_restarts_and_replays_exact_receipt(tmp_path):
    store, _, provider, payload = _setup(tmp_path)
    try:
        server = server_for(store, provider)
        assert "legacy.import" in server.initialize_result()["supported_commands"]
        first = call(server, store.project_id, payload)
        assert "result" in first, first
        receipt = first["result"]["receipt"]
        report = store.get_revision(ObjectRef.from_dict(receipt["object_refs"][-1]))["payload"]
        assert report["imported"] == 2 and report["quarantined"] == 1
        before = store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0]
        path = Path(store.conn.execute("PRAGMA database_list").fetchone()[2])
        project_id, store_id = store.project_id, store.store_id
        store.close()
        store=Store.open_project(path,project_id,store_id)
        server=server_for(store,provider)
        replay=call(server,project_id,payload)
        assert replay["result"]["receipt"] == receipt
        assert provider.calls == 1
        assert store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == before
        changed = {**payload,"import_plan_ref":{**payload["import_plan_ref"],"revision_id":"rev-404"}}
        rejected = call(server,project_id,changed)
        assert "error" in rejected
        assert provider.calls == 1
    finally:
        store.close()


def test_legacy_rpc_requires_config_and_does_not_accept_foreign_handle(tmp_path):
    store, _, provider, payload = _setup(tmp_path)
    try:
        server = server_for(store,provider,configured=False)
        assert "legacy.import" not in server.initialize_result()["supported_commands"]
        assert call(server,store.project_id,payload)["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
        server = server_for(store,provider)
        result = call(server,"foreign",payload,key="wrong-project")
        assert "error" in result and provider.calls == 0
        with pytest.raises(ValueError):
            server_for(store,provider,mode="production")
    finally:
        store.close()
