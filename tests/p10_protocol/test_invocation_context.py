"""invocation_context entry validation and handle containment (design 04 §2)."""
from __future__ import annotations

import json
import logging

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.invocation import (
    CURRENT_MACHINE_CONTEXT,
    INVOCATION_CONTEXT_FIELD,
    InteractionProof,
    InvocationContextRegistry,
    MachineContext,
    coerce_machine_context,
    sanitize_for_log,
    strip_invocation_context,
)
from project_kernel.interfaces.rpc.protocol import ProtocolServer, current_machine_context

VALID_PAYLOAD = {"title": "t", "goal": "g", "requirement_refs": [], "mode": "test"}


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _command(srv, handle, *, key="k1", payload=None, rid="1"):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.command",
           "params": {"protocol_version": "1.0.0",
                      "invocation_context_id": handle,
                      "idempotency_key": key, "command": "task.create",
                      "selector": {"project_id": "p"}, "expected_heads": [],
                      "payload": VALID_PAYLOAD if payload is None else payload}}
    return decode_frame(srv.handle_line(encode_frame(msg)))


def test_minted_handle_resolves_and_carries_principal_and_capabilities():
    clock = FakeClock()
    registry = InvocationContextRegistry(ttl_seconds=60, clock=clock)
    handle = registry.mint("user-1", {"design.write"}, project_id="proj-a")
    context = registry.resolve(handle)
    assert context is not None
    assert context.principal_id == "user-1"
    assert context.capabilities == frozenset({"design.write"})
    assert context.project_id == "proj-a"
    assert context.human_verified is False


def test_unminted_handle_is_refused_and_never_echoed():
    clock = FakeClock()
    registry = InvocationContextRegistry(clock=clock)
    with pytest.raises(KernelError) as excinfo:
        registry.resolve_required("ctx-not-minted")
    error = excinfo.value.error
    assert error.code == "PERMISSION_DENIED"
    assert error.retryable is False
    assert "ctx-not-minted" not in error.message
    assert registry.resolve("ctx-not-minted") is None


def test_expired_handle_is_refused_with_a_recovery_action():
    clock = FakeClock()
    registry = InvocationContextRegistry(ttl_seconds=30, clock=clock)
    handle = registry.mint("user-1", {"design.write"})
    clock.advance(30.0)
    assert registry.resolve(handle) is None
    with pytest.raises(KernelError) as excinfo:
        registry.resolve_required(handle)
    assert excinfo.value.error.code == "PERMISSION_DENIED"
    assert excinfo.value.error.recovery_action
    assert handle not in json.dumps(excinfo.value.error.to_dict(), ensure_ascii=False)


def test_revoked_and_purged_handles_stop_resolving():
    clock = FakeClock()
    registry = InvocationContextRegistry(ttl_seconds=10, clock=clock)
    handle = registry.mint("user-1")
    assert registry.revoke(handle) is True
    assert registry.resolve(handle) is None

    stale = registry.mint("user-2", ttl_seconds=1)
    clock.advance(2)
    assert registry.purge_expired() == 1
    assert registry.resolve(stale) is None


def test_zero_ttl_or_bad_limits_are_configuration_errors():
    with pytest.raises(ValueError):
        InvocationContextRegistry(ttl_seconds=0)
    with pytest.raises(ValueError):
        InvocationContextRegistry(max_handles=0)
    registry = InvocationContextRegistry()
    with pytest.raises(ValueError):
        registry.mint("user-1", ttl_seconds=0)


def test_human_handle_requires_verified_interaction_proof():
    registry = InvocationContextRegistry()
    for proof in (None, InteractionProof(source="cli", verified=False)):
        with pytest.raises(KernelError) as excinfo:
            registry.mint_human("user-1", {"approval.decide"}, proof=proof)
        assert excinfo.value.error.code == "HUMAN_IDENTITY_UNAVAILABLE"
    handle = registry.mint_human("user-1", {"approval.decide"},
                                 proof=InteractionProof(source="host-button", verified=True))
    assert registry.resolve(handle).human_verified is True


def test_handle_capacity_is_bounded():
    registry = InvocationContextRegistry(max_handles=2)
    first = registry.mint("u1")
    registry.mint("u2")
    registry.mint("u3")
    assert len(registry) == 2
    assert registry.resolve(first) is None


def test_coerce_accepts_tuples_and_refuses_garbage():
    assert coerce_machine_context(None) is None
    assert coerce_machine_context(("user-1", frozenset({"design.write"}))).principal_id == "user-1"
    assert coerce_machine_context(MachineContext("h", "u")).principal_id == "u"
    assert coerce_machine_context(("", frozenset())) is None
    assert coerce_machine_context("ctx1") is None


def test_server_refuses_an_unminted_handle_before_payload_validation():
    registry = InvocationContextRegistry()
    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[], context_resolver=registry.resolve)
    resp = _command(srv, "ctx-forged", payload={"role": "approver"})
    # entry identity beats payload verdicts: no payload feedback to a forged caller
    assert resp["error"]["data"]["code"] == "PERMISSION_DENIED"


def test_server_refuses_an_expired_handle():
    clock = FakeClock()
    registry = InvocationContextRegistry(ttl_seconds=5, clock=clock)
    handle = registry.mint("user-1", {"design.write"})
    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[], context_resolver=registry.resolve)
    clock.advance(6)
    resp = _command(srv, handle)
    assert resp["error"]["data"]["code"] == "PERMISSION_DENIED"
    assert handle not in json.dumps(resp, ensure_ascii=False)


def test_handler_receives_no_handle_but_sees_the_trusted_context():
    registry = InvocationContextRegistry()
    handle = registry.mint("user-1", {"design.write"}, project_id="proj-a")
    seen = {}

    def handler(command, params):
        seen["params"] = params
        seen["context"] = current_machine_context()
        return {"ok": True}

    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[], context_resolver=registry.resolve,
                         command_handler=handler)
    resp = _command(srv, handle)
    assert resp["result"] == {"ok": True}
    assert INVOCATION_CONTEXT_FIELD not in seen["params"]
    assert seen["params"]["idempotency_key"] == "k1"
    assert seen["context"].principal_id == "user-1"
    assert current_machine_context() is None  # reset after the handler returns
    assert INVOCATION_CONTEXT_FIELD not in strip_invocation_context(
        {"invocation_context_id": handle, "payload": {}})


def test_the_handle_never_reaches_logs(caplog):
    registry = InvocationContextRegistry()
    handle = registry.mint("user-1", {"design.write"})

    def handler(command, params):
        return {"receipt": {"status": "committed"}}

    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[], context_resolver=registry.resolve,
                         command_handler=handler)
    with caplog.at_level(logging.DEBUG, logger="project_kernel.rpc"):
        assert "result" in _command(srv, handle)
    assert "kernel.command" in caplog.text            # the boundary is logged
    assert handle not in caplog.text                  # ... but never the handle
    assert sanitize_for_log({"invocation_context_id": handle,
                             "nested": [{"invocation_context_id": handle}]}) == {
        "nested": [{}]}


def test_query_path_also_revalidates_the_handle():
    registry = InvocationContextRegistry()
    srv = ProtocolServer(mode="test", supported_commands=[], supported_queries=["project.overview"],
                         context_resolver=registry.resolve, query_handler=lambda q, p: {"data": {}})
    msg = {"jsonrpc": "2.0", "id": "q1", "method": "kernel.query",
           "params": {"protocol_version": "1.0.0", "invocation_context_id": "ctx-forged",
                      "selector": {"project_id": "p"}, "query": "project.overview",
                      "payload": {}}}
    resp = decode_frame(srv.handle_line(encode_frame(msg)))
    assert resp["error"]["data"]["code"] == "PERMISSION_DENIED"

    handle = registry.mint("reader", {"project.read"})
    msg["params"]["invocation_context_id"] = handle
    resp = decode_frame(srv.handle_line(encode_frame(msg)))
    assert resp["result"] == {"data": {}}


def test_current_context_is_not_leaked_into_other_threads():
    registry = InvocationContextRegistry()
    handle = registry.mint("user-1", {"design.write"})
    srv = ProtocolServer(mode="test", supported_commands=["task.create"], supported_queries=[],
                         context_resolver=registry.resolve,
                         command_handler=lambda c, p: {"ok": True})
    _command(srv, handle)
    assert CURRENT_MACHINE_CONTEXT.get() is None
