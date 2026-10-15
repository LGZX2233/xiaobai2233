"""source.ingest envelope mapping and business delegation (design 04 §4/§9)."""
from __future__ import annotations

import itertools
import json

import pytest

from project_kernel.contracts import validate_command_envelope, validate_command_payload
from project_kernel.contracts.errors import KernelError
from project_kernel.interfaces.rpc.commands import compute_input_hash, receipt_domain_for
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.ingest import (
    ObservedRange,
    SourceIngestBridge,
    SourceIngestRequest,
    SourceStreamKey,
    map_source_ingest,
)
from project_kernel.interfaces.rpc.invocation import InvocationContextRegistry
from project_kernel.interfaces.rpc.protocol import ProtocolServer

STREAM = {"host_id": "host-1", "origin_session_id": "session-1", "log_generation": "gen-1"}
PROJECT = "proj-a"


def _artifact(name: str) -> dict:
    return {"artifact_id": name, "sha256": "a" * 64, "size_bytes": "128",
            "media_type": "text/plain", "required": True}


def _event(seq, body_hash="b" * 64):
    return {"source_seq": str(seq), "payload_hash": body_hash,
            "schema_version": "1.0.0", "payload_artifact_ref": _artifact(f"art-{seq}"),
            "evidence_mode": "production"}


def _payload(seqs=(1, 2, 3), *, truncated=False, first=None, last=None):
    return {
        "source_stream": dict(STREAM),
        "events": [_event(s) for s in seqs],
        "observed_range": {"first": str(first if first is not None else min(seqs)),
                           "last": str(last if last is not None else max(seqs)),
                           "truncated": truncated},
    }


def _params(payload=None, *, key="src-1", handle="ctx-1"):
    return {"protocol_version": "1.0.0", "invocation_context_id": handle,
            "idempotency_key": key, "command": "source.ingest",
            "selector": {"project_id": PROJECT}, "expected_heads": [],
            "payload": payload if payload is not None else _payload()}


def _validated_params(**kwargs):
    params = _params(**kwargs)
    msg = {"jsonrpc": "2.0", "id": "1", "method": "kernel.command", "params": params}
    validate_command_envelope(msg)
    validate_command_payload(params["command"], params["payload"])
    return params


def test_valid_input_maps_to_a_typed_request():
    params = _validated_params()
    request = map_source_ingest(params, principal_id="user-1",
                                capabilities=frozenset({"system.ingest"}))
    assert isinstance(request, SourceIngestRequest)
    assert request.stream == SourceStreamKey("host-1", "session-1", "gen-1")
    assert request.stream_key == '["host-1","session-1","gen-1"]'
    assert request.observed_range == ObservedRange(first=1, last=3, truncated=False)
    assert [e.source_seq for e in request.events] == ["1", "2", "3"]
    assert request.receipt_domain == "project"
    assert request.input_hash == compute_input_hash(
        "source.ingest", params["selector"], params["expected_heads"], params["payload"])
    assert request.principal_id == "user-1"
    assert "invocation_context_id" not in request.to_dict()
    assert "ctx-1" not in json.dumps(request.to_dict(), ensure_ascii=False)


def test_the_handle_does_not_change_the_input_hash():
    first = map_source_ingest(_params(handle="ctx-1"))
    second = map_source_ingest(_params(handle="ctx-2"))
    assert first.input_hash == second.input_hash


def test_truncated_range_may_carry_a_subset_but_a_complete_claim_may_not():
    partial = _validated_params(payload=_payload(seqs=(1, 3), truncated=True, first=1, last=4))
    request = map_source_ingest(partial)
    assert request.observed_range.truncated is True
    assert [e.source_seq for e in request.events] == ["1", "3"]

    incomplete = _validated_params(payload=_payload(seqs=(1, 2), first=1, last=4))
    with pytest.raises(KernelError) as excinfo:
        map_source_ingest(incomplete)
    assert excinfo.value.error.code == "INVALID_INPUT"
    assert "complete" in excinfo.value.error.message


def test_duplicate_out_of_range_and_inverted_ranges_are_refused():
    duplicate = _validated_params(payload=_payload(seqs=(1, 1, 2), first=1, last=2))
    with pytest.raises(KernelError) as excinfo:
        map_source_ingest(duplicate)
    assert "duplicate source_seq" in excinfo.value.error.message

    outside = _validated_params(payload=_payload(seqs=(1, 5), first=1, last=2))
    with pytest.raises(KernelError) as excinfo:
        map_source_ingest(outside)
    assert "outside the declared observed_range" in excinfo.value.error.message

    inverted = _validated_params(payload=_payload(seqs=(2,), first=3, last=2))
    with pytest.raises(KernelError) as excinfo:
        map_source_ingest(inverted)
    assert "must not exceed" in excinfo.value.error.message


def test_leading_zero_and_non_string_sequences_are_refused():
    for bad in ("01", 1):
        params = _params()
        params["payload"]["events"][0]["source_seq"] = bad
        with pytest.raises(KernelError) as excinfo:
            map_source_ingest(params)
        assert excinfo.value.error.code == "INVALID_INPUT"


def test_receipt_domain_mapping_follows_design_04():
    assert receipt_domain_for("source.ingest") == "project"
    assert receipt_domain_for("attempt.settle") == "project"
    assert receipt_domain_for("project.provision") == "identity"
    assert receipt_domain_for("project.reconcile") == "identity"


def test_bridge_delegates_and_only_shapes_the_receipt():
    seen = {}

    class Receipt:
        def to_dict(self):
            return {"status": "committed", "command_id": "cmd-1"}

    def delegate(request):
        seen["request"] = request
        return Receipt()

    bridge = SourceIngestBridge(delegate)
    result = bridge.handle("source.ingest", _params())
    assert result == {"receipt": {"status": "committed", "command_id": "cmd-1"}}
    assert isinstance(seen["request"], SourceIngestRequest)
    assert "invocation_context_id" not in json.dumps(seen["request"].to_dict())

    with pytest.raises(KernelError) as excinfo:
        bridge.handle("attempt.settle", _params())
    assert excinfo.value.error.code == "UNSUPPORTED_COMMAND"


def test_bridge_refuses_a_delegate_that_returns_no_receipt():
    with pytest.raises(ValueError):
        SourceIngestBridge(None)
    bridge = SourceIngestBridge(lambda request: None)
    with pytest.raises(KernelError) as excinfo:
        bridge.handle("source.ingest", _params())
    assert excinfo.value.error.code == "INVALID_INPUT"


def test_server_wires_the_bridge_through_the_allowlisted_surface():
    counter = itertools.count(1)
    registry = InvocationContextRegistry(handle_factory=lambda: f"ctx-{next(counter)}")
    seen = {}

    def delegate(request):
        seen["principal"] = request.principal_id
        seen["stream"] = request.stream_key
        return {"status": "accepted", "command_id": "cmd-src-1", "operation_id": "op-1"}

    srv = ProtocolServer(mode="test", supported_commands=["source.ingest"],
                         supported_queries=[], allowlist={"source.ingest"},
                         context_resolver=registry.resolve,
                         command_handlers={"source.ingest": SourceIngestBridge(delegate).handle})
    handle = registry.mint("ingestor", {"system.ingest"})
    params = _params(handle=handle)
    msg = {"jsonrpc": "2.0", "id": "1", "method": "kernel.command", "params": params}
    resp = decode_frame(srv.handle_line(encode_frame(msg)))
    assert resp["result"]["receipt"]["status"] == "accepted"
    assert seen["principal"] == "ingestor"
    assert seen["stream"] == '["host-1","session-1","gen-1"]'


def test_the_delegate_is_not_reached_when_the_payload_is_invalid():
    registry = InvocationContextRegistry(handle_factory=lambda: "ctx-1")
    calls = []

    def delegate(request):  # pragma: no cover - must not run
        calls.append(request)
        return {"status": "committed"}

    srv = ProtocolServer(mode="test", supported_commands=["source.ingest"],
                         supported_queries=[], allowlist={"source.ingest"},
                         context_resolver=registry.resolve,
                         command_handlers={"source.ingest": SourceIngestBridge(delegate).handle})
    registry.mint("ingestor", {"system.ingest"})
    payload = _payload()
    payload["events"][0]["unexpected"] = "field"
    resp = decode_frame(srv.handle_line(encode_frame(
        {"jsonrpc": "2.0", "id": "1", "method": "kernel.command",
         "params": _params(payload, handle="ctx-1")})))
    assert resp["error"]["data"]["code"] == "INVALID_INPUT"
    assert calls == []
