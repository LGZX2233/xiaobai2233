"""Legacy import is exposed only through an explicitly configured test entry."""
from __future__ import annotations

from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame
from p01_store.helpers import make_store
from .auth_helpers import build_test_server
from p07_migration.test_entry import _setup


def _invoke(server, payload, *, key="legacy-rpc"):
    message = {"jsonrpc": "2.0", "id": key, "method": "kernel.command", "params": {
        "protocol_version": "1.0.0", "invocation_context_id": "ctx1",
        "selector": {"project_id": "proj-a"}, "command": "legacy.import",
        "payload": payload, "idempotency_key": key, "expected_heads": []}}
    return decode_frame(server.handle_line(encode_frame(message)))


def test_legacy_import_rpc_is_test_configured_and_durably_idempotent(tmp_path):
    store, service, provider, payload = _setup(tmp_path)
    try:
        server = build_test_server(store, principal="operator", legacy_config={
            "snapshot_provider": provider,
            "trusted_snapshot_producers": {"producer": {"source-a"}},
        })
        assert "legacy.import" in server.initialize_result()["supported_commands"]
        first = _invoke(server, payload)
        assert "result" in first, first
        before = store.next_commit_seq()
        restarted = build_test_server(store, principal="operator", legacy_config={
            "snapshot_provider": provider,
            "trusted_snapshot_producers": {"producer": {"source-a"}},
        })
        replay = _invoke(restarted, payload)
        assert replay == first
        assert store.next_commit_seq() == before
        assert provider.calls == 1
    finally:
        store.close()


def test_legacy_import_path_payload_is_rejected_and_default_server_disables_command(tmp_path):
    store = make_store(tmp_path, project_id="proj-a")
    try:
        disabled = build_test_server(store)
        assert "legacy.import" not in disabled.initialize_result()["supported_commands"]
        response = _invoke(disabled, {"source_root": "C:/untrusted", "source_store_id": "x",
                                      "target_project_id": "proj-a", "project_mapping": {},
                                      "batch_id": "x"})
        assert response["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
    finally:
        store.close()
