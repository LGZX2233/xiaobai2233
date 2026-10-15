"""Strict stdio framing + JSON-RPC dispatch boundaries."""
from __future__ import annotations

import json

import pytest

from project_kernel.contracts.digest import compute_bundle_digest
from project_kernel.interfaces.rpc.framing import (
    FrameError,
    FrameTooLarge,
    decode_frame,
    encode_frame,
    parse_json_strict,
)
from project_kernel.interfaces.rpc.protocol import ProtocolServer


def _roundtrip(obj):
    return decode_frame(encode_frame(obj))


def test_roundtrip_preserves_strings_and_unicode():
    obj = {"jsonrpc": "2.0", "id": "1", "result": {"msg": "中文", "n": "9007199254740993"}}
    assert _roundtrip(obj) == obj


def test_duplicate_keys_rejected():
    with pytest.raises(FrameError):
        parse_json_strict(b'{"a":1,"a":2}')


def test_non_finite_number_rejected():
    with pytest.raises(FrameError):
        parse_json_strict(b'{"a":NaN}')


def test_illegal_utf8_rejected():
    with pytest.raises(FrameError):
        parse_json_strict(b'{"a":"\xff\xfe"}')


def test_oversized_frame_rejected():
    with pytest.raises(FrameTooLarge):
        decode_frame(b"{" + b" " * 2000 + b"}", max_frame_bytes=100)


def test_initialize_returns_bundle_digest_and_limits():
    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=["project.overview"])
    line = encode_frame({"jsonrpc": "2.0", "id": "1", "method": "kernel.initialize",
                         "params": {"client_id": "c1", "supported_protocol_versions": ["1.0.0"]}})
    resp = decode_frame(srv.handle_line(line))
    assert resp["id"] == "1"
    assert resp["result"]["schema_bundle_digest"] == compute_bundle_digest()
    assert resp["result"]["mode"] == "test"
    assert resp["result"]["limits"]["max_frame_bytes"] >= 1024


def test_command_envelope_rejects_unknown_command_before_dispatch():
    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[])
    line = encode_frame({"jsonrpc": "2.0", "id": "2", "method": "kernel.command",
                         "params": {"protocol_version": "1.0.0",
                                    "invocation_context_id": "ctx1",
                                    "idempotency_key": "k1", "command": "not.a.command",
                                    "selector": {"project_id": "p1"}, "expected_heads": [],
                                    "payload": {}}})
    resp = decode_frame(srv.handle_line(line))
    assert "error" in resp  # schema validation rejects before dispatch


def test_command_dispatch_reaches_handler():
    seen = {}

    def handler(command, params):
        seen["command"] = command
        seen["payload"] = params["payload"]
        return {"ok": True}

    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[], command_handler=handler)
    line = encode_frame({"jsonrpc": "2.0", "id": "3", "method": "kernel.command",
                         "params": {"protocol_version": "1.0.0",
                                    "invocation_context_id": "ctx1",
                                    "idempotency_key": "k1", "command": "task.create",
                                    "selector": {"project_id": "p1"}, "expected_heads": [],
                                    "payload": {"title": "t", "goal": "g",
                                                "requirement_refs": [], "mode": "test"}}})
    resp = decode_frame(srv.handle_line(line))
    assert resp["result"] == {"ok": True}
    assert seen["command"] == "task.create"


def test_payload_extra_field_rejected():
    srv = ProtocolServer(mode="test", supported_commands=["task.create"], supported_queries=[])
    line = encode_frame({"jsonrpc": "2.0", "id": "4", "method": "kernel.command",
                         "params": {"protocol_version": "1.0.0",
                                    "invocation_context_id": "ctx1",
                                    "idempotency_key": "k1", "command": "task.create",
                                    "selector": {"project_id": "p1"}, "expected_heads": [],
                                    "payload": {"title": "t", "goal": "g",
                                                "requirement_refs": [], "mode": "test",
                                                "role": "approver"}}})
    resp = decode_frame(srv.handle_line(line))
    assert "error" in resp
    assert resp["error"]["data"]["code"] == "INVALID_INPUT"


def test_unknown_method_returns_method_not_found():
    srv = ProtocolServer(mode="test", supported_commands=[], supported_queries=[])
    line = encode_frame({"jsonrpc": "2.0", "id": "5", "method": "kernel.unknown",
                         "params": {}})
    resp = decode_frame(srv.handle_line(line))
    assert resp["error"]["code"] == -32601


def test_stdout_only_protocol():
    # encode_frame output is exactly one JSON line; no log prefix/whitespace noise
    data = encode_frame({"a": 1})
    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1
    json.loads(data.decode("utf-8").strip())
