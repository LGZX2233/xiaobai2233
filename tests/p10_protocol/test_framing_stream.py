"""stdio boundary: split/coalesced frames, UTF-8, size limits, log channel (AC37)."""
from __future__ import annotations

import json

import pytest

from project_kernel.interfaces.rpc.framing import (
    LineFramer,
    MAX_FRAME_BYTES_DEFAULT,
    FrameError,
    FrameTooLarge,
    decode_frame,
    encode_frame,
)
from project_kernel.interfaces.rpc.protocol import Limits, ProtocolServer


def _server(**kwargs) -> ProtocolServer:
    return ProtocolServer(mode="test",
                          supported_commands=kwargs.pop("supported_commands", ["task.create"]),
                          supported_queries=kwargs.pop("supported_queries", []), **kwargs)


def test_framer_reassembles_a_frame_split_across_chunks():
    framer = LineFramer()
    payload = encode_frame({"jsonrpc": "2.0", "id": "1", "method": "kernel.initialize"})
    assert framer.feed(payload[:10]) == []
    assert framer.pending_bytes() == 10
    frames = framer.feed(payload[10:])
    assert frames == [payload[:-1]]


def test_framer_splits_coalesced_frames_and_keeps_the_partial_tail():
    framer = LineFramer()
    first = encode_frame({"a": 1})
    second = encode_frame({"b": 2})
    tail = b'{"c":'
    frames = framer.feed(first + second + tail)
    assert frames == [first[:-1], second[:-1]]
    assert framer.pending_bytes() == len(tail)


def test_framer_split_inside_a_multi_byte_character():
    framer = LineFramer()
    line = encode_frame({"msg": "中文完成"})
    marker = "中".encode("utf-8")
    idx = line.index(marker)
    assert framer.feed(line[:idx + 1]) == []
    frames = framer.feed(line[idx + 1:])
    assert len(frames) == 1
    assert json.loads(frames[0].decode("utf-8")) == {"msg": "中文完成"}


def test_framer_accepts_crlf_and_drops_a_bare_newline():
    framer = LineFramer()
    frames = framer.feed(b'{"a":1}\r\n\n{"b":2}\n')
    assert frames == [b'{"a":1}', b"", b'{"b":2}']


def test_framer_rejects_an_unterminated_oversized_partial_frame():
    framer = LineFramer(max_frame_bytes=1024)
    with pytest.raises(FrameTooLarge):
        framer.feed(b"x" * 1025)
    assert framer.pending_bytes() == 0


def test_framer_requires_a_sane_minimum_size():
    with pytest.raises(ValueError):
        LineFramer(max_frame_bytes=16)


def test_server_feed_answers_only_complete_frames():
    srv = _server()
    init = encode_frame({"jsonrpc": "2.0", "id": "1", "method": "kernel.initialize",
                         "params": {"client_id": "c", "supported_protocol_versions": ["1.0.0"]}})
    assert srv.feed(init[:20]) == []
    rest = srv.feed(init[20:])
    assert len(rest) == 1
    assert decode_frame(rest[0])["id"] == "1"


def test_server_feed_handles_coalesced_requests_in_order():
    srv = _server(supported_queries=["project.overview"])
    q1 = encode_frame({"jsonrpc": "2.0", "id": "a", "method": "kernel.query",
                       "params": {"protocol_version": "1.0.0",
                                  "invocation_context_id": "ctx1",
                                  "selector": {"project_id": "p"},
                                  "query": "project.overview", "payload": {}}})
    q2 = encode_frame({"jsonrpc": "2.0", "id": "b", "method": "not.a.method", "params": {}})
    responses = [decode_frame(r) for r in srv.feed(q1 + q2)]
    assert [r["id"] for r in responses] == ["a", "b"]
    assert responses[0]["error"]["data"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert responses[1]["error"]["code"] == -32601


def test_server_feed_reports_an_oversized_chunk_without_dying():
    srv = _server(limits=Limits(max_frame_bytes=1024, max_inflight=2))
    responses = [decode_frame(r) for r in srv.feed(b"z" * 2048)]
    assert len(responses) == 1
    assert responses[0]["error"]["code"] == -32600
    # the framer recovered: the next well-formed frame is still served
    good = encode_frame({"jsonrpc": "2.0", "id": "1", "method": "not.a.method", "params": {}})
    assert decode_frame(srv.handle_line(good[:-1]))["error"]["code"] == -32601


def test_a_valid_frame_sharing_a_chunk_with_an_oversized_partial_is_still_served():
    srv = _server(limits=Limits(max_frame_bytes=1024, max_inflight=2))
    good = encode_frame({"jsonrpc": "2.0", "id": "keep", "method": "not.a.method",
                         "params": {}})
    responses = [decode_frame(r) for r in srv.feed(good + b"z" * 2048)]
    assert [r["id"] for r in responses] == ["keep", None]
    assert responses[1]["error"]["code"] == -32600


def test_illegal_utf8_duplicate_keys_and_non_finite_are_parse_errors():
    srv = _server()
    for line in (b'{"a":"\xff\xfe"}', b'{"a":1,"a":2}', b'{"a":NaN}'):
        resp = decode_frame(srv.handle_line(line))
        assert resp["error"]["code"] == -32700, line
    with pytest.raises(FrameError):
        decode_frame(b"[1,2]")  # top-level must be an object


def test_unknown_fields_are_rejected_at_each_layer():
    srv = _server()
    envelope_extra = encode_frame({
        "jsonrpc": "2.0", "id": "1", "method": "kernel.command",
        "params": {"protocol_version": "1.0.0", "invocation_context_id": "ctx-1",
                   "idempotency_key": "k1", "command": "task.create",
                   "selector": {"project_id": "p"}, "expected_heads": [],
                   "payload": {"title": "t", "goal": "g", "requirement_refs": [],
                               "mode": "test"},
                   "actor_id": "admin"}})
    resp = decode_frame(srv.handle_line(envelope_extra[:-1]))
    assert resp["error"]["data"]["code"] == "INVALID_INPUT"

    payload_extra = encode_frame({
        "jsonrpc": "2.0", "id": "2", "method": "kernel.command",
        "params": {"protocol_version": "1.0.0", "invocation_context_id": "ctx-1",
                   "idempotency_key": "k2", "command": "task.create",
                   "selector": {"project_id": "p"}, "expected_heads": [],
                   "payload": {"title": "t", "goal": "g", "requirement_refs": [],
                               "mode": "test", "role": "approver"}}})
    resp = decode_frame(srv.handle_line(payload_extra[:-1]))
    assert resp["error"]["data"]["code"] == "INVALID_INPUT"


def test_stdout_only_protocol_has_no_log_noise():
    srv = _server()
    data = srv.handle_line(encode_frame({"jsonrpc": "2.0", "id": "1",
                                         "method": "not.a.method", "params": {}}))
    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1
    assert data.startswith(b"{")
    assert MAX_FRAME_BYTES_DEFAULT > 1024


def test_responses_echo_the_request_id_so_a_client_can_bind_out_of_order():
    srv = _server()
    second = encode_frame({"jsonrpc": "2.0", "id": "b2", "method": "not.a.method", "params": {}})
    first = encode_frame({"jsonrpc": "2.0", "id": "a1", "method": "not.a.method", "params": {}})
    responses = [decode_frame(r) for r in srv.feed(second + first)]
    assert [r["id"] for r in responses] == ["b2", "a1"]
    assert all(r["error"]["code"] == -32601 for r in responses)
