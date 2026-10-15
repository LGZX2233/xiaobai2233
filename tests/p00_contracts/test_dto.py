"""Typed DTO construction, validation and enum coverage."""
from __future__ import annotations

import pytest

from project_kernel.contracts import (
    CommandName,
    QueryName,
    ObjectRef,
    Selector,
    ExpectedHead,
    ResolvedScope,
    CommandContext,
    CommandReceipt,
    Cursor,
    FactValue,
    DeliverySnapshotBody,
)
from project_kernel.contracts.errors import BlockError, KernelError, stale_revision
from project_kernel.contracts.validation import ValidationError


def test_object_ref_rejects_bad_ids():
    with pytest.raises(ValueError):
        ObjectRef("", "task", "t", "r")  # empty project_id
    with pytest.raises(ValueError):
        ObjectRef("p", "task", "t", "r e")  # space in revision_id


def test_object_ref_round_trip():
    r = ObjectRef("p1", "task", "t1", "r1")
    assert ObjectRef.from_dict(r.to_dict()) == r


def test_selector_rejects_missing_project():
    with pytest.raises(ValueError):
        Selector("")
    s = Selector("p1", task_id="t1")
    assert s.to_dict() == {"project_id": "p1", "task_id": "t1"}


def test_resolved_scope_requires_explicit_project_and_principal():
    scope = ResolvedScope(project_id="p1", store_id="s1", principal_id="u1",
                          capabilities=frozenset({"project.read"}), mode="test")
    assert scope.has("project.read")
    assert not scope.has("approval.decide")
    with pytest.raises(ValueError):
        ResolvedScope(project_id="", store_id="s1", principal_id="u1",
                      capabilities=frozenset(), mode="test")


def test_command_context_requires_digest_input_hash():
    scope = ResolvedScope("p1", "s1", "u1", frozenset(), "test")
    ctx = CommandContext(scope=scope, command_id="c1", idempotency_key="k1",
                         input_hash="a" * 64)
    assert ctx.command_id == "c1"
    with pytest.raises(ValueError):
        CommandContext(scope=scope, command_id="c1", idempotency_key="k1", input_hash="zz")


def test_block_error_and_kernel_error():
    e = stale_revision()
    assert e.code == "STALE_REVISION"
    assert e.retryable is False
    assert e.category == "conflict"
    k = KernelError(e)
    assert k.error is e
    d = e.to_dict()
    assert BlockError.from_dict(d) == e


def test_validation_error_wraps_block_error():
    with pytest.raises(ValidationError) as exc:
        from project_kernel.contracts import validate_command_payload
        validate_command_payload("task.create", {"title": "t", "goal": "g",
                                                 "requirement_refs": [], "mode": "test",
                                                 "extra": 1})
    assert exc.value.error.code == "INVALID_INPUT"


def test_enums_are_44_and_14():
    assert len(list(CommandName)) == 44
    assert len(list(QueryName)) == 14


def test_fact_value_unknown_is_not_known():
    assert FactValue().is_known is False
    assert FactValue(known="x").is_known is True
