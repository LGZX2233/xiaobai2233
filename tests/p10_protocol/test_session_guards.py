"""Session guards: in-flight limit and receipt replay/reconnect (AC38)."""
from __future__ import annotations

import itertools
import threading

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.invocation import InvocationContextRegistry
from project_kernel.interfaces.rpc.protocol import Limits, ProtocolServer
from project_kernel.interfaces.rpc.session import (
    REPLAY_CONFLICT,
    REPLAY_HIT,
    REPLAY_NEW,
    InFlightLimiter,
    ReceiptLedger,
)

VALID_PAYLOAD = {"title": "t", "goal": "g", "requirement_refs": [], "mode": "test"}
PROJECT = "p"


def _command(srv, key, *, payload=None, command="task.create", rid="1"):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.command",
           "params": {"protocol_version": "1.0.0",
                      "invocation_context_id": "ctx-1",
                      "idempotency_key": key, "command": command,
                      "selector": {"project_id": PROJECT}, "expected_heads": [],
                      "payload": VALID_PAYLOAD if payload is None else payload}}
    return decode_frame(srv.handle_line(encode_frame(msg)))


def _server(**kwargs):
    registry = kwargs.pop("registry", None)
    if registry is None:
        counter = itertools.count(1)
        registry = InvocationContextRegistry(
            handle_factory=lambda: f"ctx-{next(counter)}")
    handle = kwargs.pop("handle", None) or registry.mint("user-1", {"design.write"})
    srv = ProtocolServer(mode="test", supported_commands=["task.create"], supported_queries=[],
                         context_resolver=registry.resolve, **kwargs)
    return srv, handle, registry


# -- in-flight ----------------------------------------------------------------
def test_in_flight_limiter_refuses_beyond_the_capacity_and_recovers():
    limiter = InFlightLimiter(max_inflight=2)
    limiter.try_acquire()
    limiter.try_acquire()
    assert limiter.in_flight == 2
    with pytest.raises(KernelError) as excinfo:
        limiter.try_acquire()
    assert excinfo.value.error.code == "TEMPORARY_UNAVAILABLE"
    assert excinfo.value.error.retryable is True
    limiter.release()
    limiter.try_acquire()
    assert limiter.in_flight == 2
    for _ in range(4):
        limiter.release()
    assert limiter.in_flight == 0


def test_in_flight_limiter_requires_a_positive_capacity():
    with pytest.raises(ValueError):
        InFlightLimiter(0)


def test_the_advertised_in_flight_limit_is_enforced_by_default():
    srv = ProtocolServer(mode="test", supported_commands=["task.create"], supported_queries=[],
                         limits=Limits(max_inflight=3),
                         command_handler=lambda c, p: {"ok": True})
    assert srv.inflight.max_inflight == 3 == srv.initialize_result()["limits"]["max_inflight"]
    with pytest.raises(ValueError):
        ProtocolServer(mode="test", supported_commands=[], supported_queries=[],
                       limits=Limits(max_inflight=0))


def test_server_refuses_an_extra_request_instead_of_queueing():
    started, release = threading.Event(), threading.Event()

    def handler(command, params):
        started.set()
        assert release.wait(timeout=10)
        return {"ok": True}

    srv, handle, _ = _server(inflight=InFlightLimiter(1), command_handler=handler)
    worker = threading.Thread(target=lambda: _command(srv, "k1"), daemon=True)
    worker.start()
    assert started.wait(timeout=10), "handler never started"
    try:
        resp = _command(srv, "k2", rid="2")
        assert resp["error"]["data"]["code"] == "TEMPORARY_UNAVAILABLE"
        assert resp["error"]["data"]["retryable"] is True
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive()


def test_in_flight_slot_is_released_after_a_failure():
    def boom(command, params):
        raise RuntimeError("boom")

    limiter = InFlightLimiter(1)
    srv, handle, _ = _server(inflight=limiter, command_handler=boom)
    resp = _command(srv, "k1")
    assert resp["error"]["data"]["code"] == "TEMPORARY_UNAVAILABLE"
    assert limiter.in_flight == 0


# -- receipt ledger -----------------------------------------------------------
def test_ledger_replays_same_hash_and_refuses_a_different_hash():
    ledger = ReceiptLedger()
    assert ledger.begin("u", "k", "h1") == (REPLAY_NEW, None)
    ledger.record("u", "k", "h1", {"status": "committed", "command_id": "c1"})
    state, cached = ledger.begin("u", "k", "h1")
    assert state == REPLAY_HIT and cached["command_id"] == "c1"
    state, cached = ledger.begin("u", "k", "h2")
    assert state == REPLAY_CONFLICT and cached["command_id"] == "c1"
    assert ledger.lookup("u", "k")["command_id"] == "c1"
    assert ledger.lookup("other-user", "k") is None  # never cross principals


def test_ledger_never_manufactures_a_receipt():
    ledger = ReceiptLedger()
    ledger.record("u", "k", "h1", {"ok": True})          # not a receipt shape
    ledger.record("u", "k", "h1", None)
    assert len(ledger) == 0
    assert ledger.lookup("u", "k") is None


def test_ledger_is_bounded():
    ledger = ReceiptLedger(max_entries=1)
    ledger.record("u", "k1", "h1", {"status": "committed"})
    ledger.record("u", "k2", "h2", {"status": "committed"})
    assert ledger.lookup("u", "k1") is None
    assert ledger.lookup("u", "k2") is not None
    with pytest.raises(ValueError):
        ReceiptLedger(max_entries=0)


def test_server_replays_the_original_receipt_for_a_retry():
    calls = []

    def handler(command, params):
        calls.append(params["idempotency_key"])
        return {"receipt": {"status": "committed", "command_id": "cmd-1",
                            "idempotency_key": params["idempotency_key"]}}

    srv, handle, _ = _server(command_handler=handler, receipt_ledger=ReceiptLedger())
    first = _command(srv, "k1")
    second = _command(srv, "k1", rid="2")
    assert first["result"] == second["result"]
    assert calls == ["k1"], "a same-key/same-hash retry must not re-dispatch"
    assert srv.replay_receipt("user-1", "k1")["command_id"] == "cmd-1"


def test_server_refuses_a_same_key_with_different_content():
    calls = []

    def handler(command, params):
        calls.append(params["idempotency_key"])
        return {"receipt": {"status": "committed", "command_id": "cmd-1"}}

    srv, handle, _ = _server(command_handler=handler, receipt_ledger=ReceiptLedger())
    _command(srv, "k1")
    conflict = _command(srv, "k1", payload={**VALID_PAYLOAD, "title": "changed"}, rid="2")
    assert conflict["error"]["data"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert conflict["error"]["data"]["retryable"] is False
    assert calls == ["k1"]


def test_server_replays_a_rejected_receipt_unchanged():
    calls = []

    def handler(command, params):
        calls.append(params["idempotency_key"])
        return {"receipt": {"status": "rejected", "command_id": "cmd-1",
                            "error": {"code": "STALE_REVISION"}}}

    srv, handle, _ = _server(command_handler=handler, receipt_ledger=ReceiptLedger())
    first = _command(srv, "k1")
    second = _command(srv, "k1", rid="2")
    assert first["result"] == second["result"]
    assert calls == ["k1"]


def test_replay_requires_a_resolved_principal():
    srv = ProtocolServer(mode="test", supported_commands=["task.create"], supported_queries=[],
                         command_handler=lambda c, p: {"ok": True},
                         receipt_ledger=ReceiptLedger())
    resp = _command(srv, "k1")
    assert resp["error"]["data"]["code"] == "CAPABILITY_UNAVAILABLE"


def test_the_original_receipt_survives_a_different_handle_and_connection():
    calls = []

    def handler(command, params):
        calls.append(params["idempotency_key"])
        return {"receipt": {"status": "committed", "command_id": "cmd-1"}}

    counter = itertools.count(1)
    registry = InvocationContextRegistry(handle_factory=lambda: f"ctx-{next(counter)}")
    srv = ProtocolServer(mode="test", supported_commands=["task.create"], supported_queries=[],
                         context_resolver=registry.resolve,
                         command_handler=handler, receipt_ledger=ReceiptLedger())
    first_handle = registry.mint("user-1", {"design.write"})
    _command_with(srv, first_handle, "k1")
    # reconnect: a freshly minted handle for the same principal must still replay
    second_handle = registry.mint("user-1", {"design.write"})
    assert second_handle != first_handle
    replay = _command_with(srv, second_handle, "k1", rid="2")
    assert replay["result"]["receipt"]["command_id"] == "cmd-1"
    assert calls == ["k1"], "the handle must not influence idempotency"


def _command_with(srv, handle, key, *, rid="1"):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.command",
           "params": {"protocol_version": "1.0.0",
                      "invocation_context_id": handle,
                      "idempotency_key": key, "command": "task.create",
                      "selector": {"project_id": PROJECT}, "expected_heads": [],
                      "payload": VALID_PAYLOAD}}
    return decode_frame(srv.handle_line(encode_frame(msg)))
