"""Decisive-input projection for snapshot eligibility (P04).

Eligibility must fail on *decisive* changes (requirements, acceptance, rules,
scope, candidate content, delivery target, verification basis) and must not fail
on unrelated display names or ordinary audit noise. Comparing whole task rows is
explicitly not allowed, so each referenced object is reduced to the fields that
actually feed the delivery decision.
"""
from __future__ import annotations

from typing import Any, Mapping

#: fields that never change a delivery decision
NON_DECISIVE_KEYS = frozenset({
    "display_name", "title", "summary", "notes", "created_at", "updated_at",
    "committed_at", "reason", "comment",
})

#: per-type allow-lists of decisive fields (everything else is dropped)
_KEEP: dict[str, tuple[str, ...]] = {
    # a task's phase/blockers move during the delivery itself and must not
    # invalidate the snapshot it is currently approving
    "task": ("requirement_refs", "packet_ref", "terminal_outcome"),
    # attempt status/exit code settle before the snapshot and are not inputs
    "attempt": ("packet_ref", "strategy_id", "execution_root_ref", "mode"),
    "verification": ("attempt_ref", "candidate_manifest_ref", "candidate_digest",
                     "acceptance_refs", "acceptance_basis", "result", "passed",
                     "validity", "evidence_mode", "human_checks"),
}


def decisive_projection(object_type: str, payload: Any) -> Any:
    """Reduce an object payload to the fields that feed the delivery decision."""
    if not isinstance(payload, Mapping):
        return payload
    keep = _KEEP.get(object_type)
    if keep is not None:
        return {k: payload[k] for k in keep if k in payload}
    return {k: v for k, v in payload.items() if k not in NON_DECISIVE_KEYS}


def ref_key(ref: Mapping[str, Any]) -> str:
    return f"{ref['object_type']}:{ref['object_id']}"


def iter_refs(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    """All decisive refs of a DeliverySnapshot body, normalised to a list."""
    refs: list[dict[str, Any]] = []
    for name in ("task_ref", "packet_ref", "selected_attempt_ref", "scope_ref",
                 "input_manifest_ref", "context_manifest_ref", "environment_ref"):
        ref = body.get(name)
        if isinstance(ref, Mapping):
            refs.append(dict(ref))
    for name in ("requirement_refs", "design_refs", "acceptance_refs", "rule_refs",
                 "verification_refs"):
        for ref in body.get(name, ()) or ():
            if isinstance(ref, Mapping):
                refs.append(dict(ref))
    delivery = body.get("delivery")
    if isinstance(delivery, Mapping) and isinstance(delivery.get("target_ref"), Mapping):
        refs.append(dict(delivery["target_ref"]))
    return refs
