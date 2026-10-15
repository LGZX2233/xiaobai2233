"""Exact project references and frozen command validation shared by workflow services."""
from __future__ import annotations
from copy import deepcopy
from collections.abc import Mapping
from typing import Any
from jsonschema import ValidationError
from ...contracts import validate_command_payload
from ...contracts.dto import ObjectRef
from ...contracts.errors import KernelError, invalid_input, reference_not_found, scope_mismatch

def checked_payload(command: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = deepcopy(dict(payload))
    try:
        validate_command_payload(command, body)
    except (ValidationError, ValueError, TypeError) as exc:
        raise KernelError(invalid_input(f"invalid {command} payload")) from exc
    return body

def exact(store, raw: Any, kind: str | None = None):
    try:
        ref = raw if isinstance(raw, ObjectRef) else ObjectRef.from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise KernelError(invalid_input("invalid object reference")) from exc
    if ref.project_id != store.project_id:
        raise KernelError(scope_mismatch("reference belongs to another project"))
    if kind is not None and ref.object_type != kind:
        raise KernelError(invalid_input(f"expected {kind} reference"))
    rev = store.get_revision(ref)
    if rev is None:
        raise KernelError(reference_not_found(f"{ref.object_type}/{ref.object_id}@{ref.revision_id} not found"))
    return ref, rev

def validate_refs(store, value: Any) -> None:
    if isinstance(value, Mapping):
        if {"project_id", "object_type", "object_id", "revision_id"} <= value.keys():
            exact(store, value)
        else:
            for child in value.values():
                validate_refs(store, child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_refs(store, child)

def current(store, raw: Any, kind: str | None = None, pointer: str = "current"):
    ref, rev = exact(store, raw, kind)
    head = store.get_head(ref.object_type, ref.object_id, pointer)
    if head is None or head["revision_id"] != ref.revision_id:
        from ...contracts.errors import stale_revision
        raise KernelError(stale_revision(f"{ref.object_type}/{ref.object_id} is not the {pointer} revision"))
    return ref, rev
