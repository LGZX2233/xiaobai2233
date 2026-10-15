"""Machine command surface vs allowlist vs declared protocol surface (design 04 §1/§4)."""
from __future__ import annotations

import pytest

from project_kernel.bootstrap import HUMAN_ONLY_COMMANDS as ROOT_HUMAN_ONLY
from project_kernel.bootstrap import MACHINE_COMMAND_ALLOWLIST, build_server, InvocationContextRegistry
from project_kernel.contracts import ALL_COMMAND_NAMES
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.policy import (
    HUMAN_ONLY_COMMANDS,
    CommandSurface,
    ProtocolSurfaceError,
    build_surface,
)
from project_kernel.interfaces.rpc.protocol import ProtocolServer

from p01_store.helpers import make_store

VALID_PAYLOAD = {"title": "t", "goal": "g", "requirement_refs": [], "mode": "test"}


def _command(srv, command, *, payload=None, key="k1", rid="1"):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.command",
           "params": {"protocol_version": "1.0.0",
                      "invocation_context_id": "ctx-1",
                      "idempotency_key": key, "command": command,
                      "selector": {"project_id": "p"}, "expected_heads": [],
                      "payload": VALID_PAYLOAD if payload is None else payload}}
    return decode_frame(srv.handle_line(encode_frame(msg)))


def test_declared_surface_may_not_exceed_the_allowlist():
    with pytest.raises(ProtocolSurfaceError):
        CommandSurface(allowlist=frozenset({"task.create"}),
                       supported=frozenset({"task.create", "attempt.start"}))


def test_declared_surface_may_not_expose_human_only_commands():
    with pytest.raises(ProtocolSurfaceError):
        CommandSurface(allowlist=frozenset({"task.create", "approval.decide"}),
                       supported=frozenset({"approval.decide"}))


def test_machine_allowlist_may_not_contain_human_only_commands():
    with pytest.raises(ProtocolSurfaceError):
        CommandSurface(allowlist=frozenset({"decision.record"}),
                       supported=frozenset({"decision.record"}))


def test_surface_names_must_exist_in_the_frozen_catalog():
    with pytest.raises(ProtocolSurfaceError):
        build_surface(allowlist={"task.create", "invented.command"},
                      supported_commands={"task.create"}, catalog=ALL_COMMAND_NAMES)
    surface = build_surface(allowlist={"task.create"}, supported_commands={"task.create"},
                            catalog=ALL_COMMAND_NAMES)
    assert surface.declared() == ("task.create",)


def test_human_only_is_refused_before_the_payload_is_validated():
    # A mis-wiring that declares a human-only command must still refuse it as
    # UNSUPPORTED_COMMAND, never leak a payload verdict.
    srv = ProtocolServer(mode="test", supported_commands=["approval.decide"],
                         supported_queries=[])
    resp = _command(srv, "approval.decide", payload={})
    assert resp["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"


def test_an_allowlist_that_claims_a_human_only_command_fails_at_composition():
    with pytest.raises(ProtocolSurfaceError):
        ProtocolServer(mode="test", supported_commands=["approval.decide"],
                       supported_queries=[], allowlist={"approval.decide"})


def test_not_allowlisted_and_not_wired_commands_are_unsupported():
    srv = ProtocolServer(mode="test", supported_commands=["task.create"],
                         supported_queries=[],
                         allowlist={"task.create", "attempt.start"})
    not_allowed = _command(srv, "task.terminate", payload={})
    assert not_allowed["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
    not_wired = _command(srv, "attempt.start", payload={})
    assert not_wired["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
    assert "not wired" in not_wired["error"]["message"]

    served = _command(srv, "task.create")
    assert served["error"]["data"]["code"] == "CAPABILITY_UNAVAILABLE"  # no handler yet


def test_initialize_advertises_the_consistent_surface():
    srv = ProtocolServer(mode="test",
                         supported_commands=["task.create", "attempt.start"],
                         supported_queries=["project.overview"],
                         allowlist={"task.create", "attempt.start", "delivery.apply"})
    result = srv.initialize_result()
    assert result["supported_commands"] == ["attempt.start", "task.create"]
    assert set(result["supported_commands"]) <= set(MACHINE_COMMAND_ALLOWLIST)
    assert not set(result["supported_commands"]) & HUMAN_ONLY_COMMANDS


def test_rpc_human_only_matches_the_composition_root():
    assert HUMAN_ONLY_COMMANDS == frozenset(ROOT_HUMAN_ONLY)


def test_the_real_composition_root_is_surface_consistent(tmp_path):
    store = make_store(tmp_path, project_id="proj-a")
    try:
        srv = build_server(store, contexts=InvocationContextRegistry(), principal="user-1", mode="test")
        declared = set(srv.initialize_result()["supported_commands"])
        assert declared <= set(MACHINE_COMMAND_ALLOWLIST)
        assert not declared & set(ROOT_HUMAN_ONLY)
        # the allowlist must be buildable as a surface against the frozen catalog
        surface = build_surface(allowlist=MACHINE_COMMAND_ALLOWLIST,
                                supported_commands=declared, catalog=ALL_COMMAND_NAMES)
        assert surface.declared() == tuple(sorted(declared))
        for human_only in ROOT_HUMAN_ONLY:
            assert surface.reject(human_only).code == "UNSUPPORTED_COMMAND"
    finally:
        store.close()
