"""P10/P13 machine allowlist + invocation context validation."""
from __future__ import annotations

from project_kernel.bootstrap import (
    HUMAN_ONLY_COMMANDS,
    MACHINE_COMMAND_ALLOWLIST,
    InvocationContextRegistry,
    build_server,
)
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame

from p01_store.helpers import make_store

PROJ = "proj-a"


def _command(srv, rid, key, command, payload, context_id="ctx1"):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.command",
           "params": {"protocol_version": "1.0.0", "invocation_context_id": context_id,
                      "idempotency_key": key, "command": command,
                      "selector": {"project_id": PROJ}, "expected_heads": [],
                      "payload": payload}}
    return decode_frame(srv.handle_line(encode_frame(msg)))


def test_human_only_commands_are_not_in_machine_allowlist():
    assert "approval.decide" in HUMAN_ONLY_COMMANDS
    assert "approval.decide" not in MACHINE_COMMAND_ALLOWLIST
    assert "decision.record" in HUMAN_ONLY_COMMANDS
    assert "verification.record_review" in HUMAN_ONLY_COMMANDS


def test_unminted_invocation_context_is_rejected(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    reg = InvocationContextRegistry()
    srv = build_server(store, principal="user-1", contexts=reg, mode="test")
    try:
        r = _command(srv, "1", "k1", "task.create",
                     {"title": "t", "goal": "g", "requirement_refs": [], "mode": "test"},
                     context_id="ctx-not-minted")
        assert "error" in r
        assert r["error"]["data"]["code"] == "PERMISSION_DENIED"
    finally:
        store.close()


def test_minted_context_works(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    reg = InvocationContextRegistry()
    handle = reg.mint("user-1", frozenset({"design.write"}), project_id=PROJ)
    srv = build_server(store, principal="user-1", contexts=reg, mode="test")
    try:
        r = _command(srv, "1", "k1", "task.create",
                     {"title": "t", "goal": "g", "requirement_refs": [], "mode": "test"},
                     context_id=handle)
        assert "result" in r
    finally:
        store.close()


def test_approval_decide_not_registered_in_server(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    reg = InvocationContextRegistry()
    handle = reg.mint("user-1", frozenset({"approval.decide"}), project_id=PROJ)
    srv = build_server(store, principal="user-1", contexts=reg, mode="test")
    try:
        r = _command(srv, "1", "k1", "approval.decide",
                     {"approval_id": "a", "decision": "approved",
                      "snapshot_digest": "a" * 64, "reason": ""}, context_id=handle)
        assert "error" in r
        assert r["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
    finally:
        store.close()
