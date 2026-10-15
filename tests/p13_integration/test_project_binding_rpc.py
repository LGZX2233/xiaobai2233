"""Project binding is discoverable only when its registry is configured."""
from project_kernel.data.store.store import Store
from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame
from p01_store.test_project_binding_entry import _setup, _payload
from p13_integration.auth_helpers import build_test_server
from p13_integration.test_closed_loop import call


def test_project_binding_public_entry_restart_and_historical_status(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        server = build_test_server(store, principal="operator", identity_registry=registry)
        payload = _payload()
        receipt = call(server, "proj-a", "project.bind", payload, "bind-rpc")
        assert receipt["receipt_domain"] == "project" and receipt["status"] == "accepted"
        query = {"operation_id": receipt["operation_id"]}
        operation = call(server, "proj-a", "operation.status", query, query=True)["data"]
        assert operation["status"] == "completed"
        stored = call(server, "proj-a", "command.receipt",
            {"receipt_domain": "project", "idempotency_key": "bind-rpc"}, query=True)["data"]
        assert stored["receipt"] == receipt
        path = store.conn.execute("PRAGMA database_list").fetchone()[2]
        store_id = store.store_id
        store.close()
        store = Store.open_project(path, "proj-a", store_id)
        server = build_test_server(store, principal="operator", identity_registry=registry)
        assert call(server, "proj-a", "project.bind", payload, "bind-rpc") == receipt
        assert registry.conn.execute("SELECT COUNT(*) FROM identity_binding").fetchone()[0] == 1
        response = decode_frame(server.handle_line(encode_frame({
            "jsonrpc": "2.0", "id": "history", "method": "kernel.query", "params": {
                "protocol_version": "1.0.0", "invocation_context_id": "ctx1",
                "selector": {"project_id": "proj-a"}, "query": "operation.status", "payload": query,
                "as_of_seq": receipt["commit_seq"]}})))
        assert response["result"]["data"]["status"] == "pending"
    finally:
        store.close()
        registry.close()


def test_project_binding_unconfigured_entry_does_not_advertise(tmp_path):
    registry, store = _setup(tmp_path)
    try:
        server = build_test_server(store, principal="operator")
        response = decode_frame(server.handle_line(encode_frame({"jsonrpc": "2.0", "id": "bind",
            "method": "kernel.command", "params": {"protocol_version": "1.0.0",
            "invocation_context_id": "ctx1", "selector": {"project_id": "proj-a"},
            "command": "project.bind", "payload": _payload(), "expected_heads": [],
            "idempotency_key": "unconfigured"}})))
        assert response["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
        assert registry.conn.execute("SELECT COUNT(*) FROM identity_binding").fetchone()[0] == 0
    finally:
        store.close()
        registry.close()
