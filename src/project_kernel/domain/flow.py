"""Pure execution-flow state rules (P04 early milestone: flow_rules_ready).

No I/O, no DB, no provider. Single source of truth for Task phase transitions,
blocker handling (phase/blocker separated), verification result computation,
approval identity guard, and delivery/epoch/fencing rules. P02 and P03 consume
these functions; they must not re-implement the state table.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..contracts import (
    ApprovalStatus,
    AttemptStatus,
    DeliveryState,
    ErrorCode,
    TaskPhase,
    VerificationStatus,
)
from ..contracts.dto import AcceptanceItem, CheckResult
from ..contracts.errors import BlockError, invalid_input


@dataclass(frozen=True)
class ProposedTransition:
    from_state: str
    to_state: str
    command: str

    @property
    def changed(self) -> bool:
        return self.from_state != self.to_state


@dataclass(frozen=True)
class Rejection:
    from_state: str
    command: str
    error: BlockError


_TASK_TRANSITIONS: dict[str, dict[str, str]] = {
    TaskPhase.DRAFT.value: {
        "task.create": TaskPhase.DRAFT.value,
        "requirement.save": TaskPhase.DESIGNING.value,
        "requirement.confirm": TaskPhase.DESIGNING.value,
        "design.save": TaskPhase.DESIGNING.value,
        "design.confirm": TaskPhase.DESIGNING.value,
        "dispatch.draft": TaskPhase.DRAFT.value,
        "dispatch.confirm": TaskPhase.DISPATCH_READY.value,
    },
    TaskPhase.DESIGNING.value: {
        "requirement.save": TaskPhase.DESIGNING.value,
        "design.save": TaskPhase.DESIGNING.value,
        "dispatch.draft": TaskPhase.DESIGNING.value,
        "dispatch.confirm": TaskPhase.DISPATCH_READY.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.DISPATCH_READY.value: {
        "dispatch.revoke": TaskPhase.DESIGNING.value,
        "attempt.start": TaskPhase.EXECUTING.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.EXECUTING.value: {
        "attempt.start": TaskPhase.EXECUTING.value,
        "attempt.settle": TaskPhase.EXECUTING.value,
        "verification.run": TaskPhase.VERIFYING.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.VERIFYING.value: {
        "verification.run": TaskPhase.VERIFYING.value,
        "verification.passed": TaskPhase.DELIVERY_READY.value,
        "attempt.select": TaskPhase.DELIVERY_READY.value,
        "attempt.start": TaskPhase.EXECUTING.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.DELIVERY_READY.value: {
        "delivery.request": TaskPhase.APPROVAL_PENDING.value,
        "attempt.start": TaskPhase.EXECUTING.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.APPROVAL_PENDING.value: {
        "approval.rejected": TaskPhase.DELIVERY_READY.value,
        "approval.revoked": TaskPhase.DELIVERY_READY.value,
        "approval.superseded": TaskPhase.DELIVERY_READY.value,
        "approval.expired": TaskPhase.DELIVERY_READY.value,
        "approval.approved": TaskPhase.DELIVERING.value,
        "delivery.start": TaskPhase.DELIVERING.value,
        "attempt.start": TaskPhase.EXECUTING.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.DELIVERING.value: {
        "delivery.applied": TaskPhase.CLOSED.value,
        "delivery.start": TaskPhase.DELIVERING.value,
        "approval.revoked": TaskPhase.DELIVERY_READY.value,
        "approval.expired": TaskPhase.DELIVERY_READY.value,
        "approval.superseded": TaskPhase.DELIVERY_READY.value,
        "task.close": TaskPhase.CLOSED.value,
        "task.terminate": TaskPhase.CLOSED.value,
    },
    TaskPhase.CLOSED.value: {},
}

_ATTEMPT_TRANSITIONS: dict[str, set[str]] = {
    AttemptStatus.PLANNED.value: {AttemptStatus.STARTING.value},
    AttemptStatus.STARTING.value: {
        AttemptStatus.RUNNING.value, AttemptStatus.FAILED.value, AttemptStatus.UNKNOWN.value,
    },
    AttemptStatus.RUNNING.value: {
        AttemptStatus.COMPLETED.value, AttemptStatus.FAILED.value,
        AttemptStatus.CANCELLED.value, AttemptStatus.INTERRUPTED.value,
        AttemptStatus.UNKNOWN.value,
    },
    AttemptStatus.UNKNOWN.value: {AttemptStatus.RUNNING.value, AttemptStatus.COMPLETED.value,
                                  AttemptStatus.FAILED.value, AttemptStatus.CANCELLED.value},
    AttemptStatus.COMPLETED.value: set(),
    AttemptStatus.FAILED.value: set(),
    AttemptStatus.CANCELLED.value: set(),
    AttemptStatus.INTERRUPTED.value: set(),
}

_DELIVERY_TRANSITIONS: dict[str, set[str]] = {
    DeliveryState.PREPARED.value: {DeliveryState.CLAIMED.value},
    DeliveryState.CLAIMED.value: {DeliveryState.APPLYING.value, DeliveryState.PREPARED.value},
    DeliveryState.APPLYING.value: {
        DeliveryState.APPLIED.value, DeliveryState.FAILED.value, DeliveryState.UNKNOWN.value,
    },
    DeliveryState.UNKNOWN.value: {DeliveryState.APPLIED.value, DeliveryState.FAILED.value},
    DeliveryState.APPLIED.value: set(),
    DeliveryState.FAILED.value: set(),
}


def task_transition(current_phase: str, command: str) -> ProposedTransition | Rejection:
    if current_phase not in _TASK_TRANSITIONS:
        return Rejection(current_phase, command, invalid_input(f"unknown phase {current_phase!r}"))
    allowed = _TASK_TRANSITIONS.get(current_phase, {})
    if command not in allowed:
        return Rejection(current_phase, command,
                         invalid_input(f"command {command!r} is not allowed in phase {current_phase!r}"))
    return ProposedTransition(current_phase, allowed[command], command)


def closed_is_terminal(phase: str) -> bool:
    return phase == TaskPhase.CLOSED.value


def attempt_transition(current_status: str, target_status: str) -> bool:
    return target_status in _ATTEMPT_TRANSITIONS.get(current_status, set())


def attempt_is_terminal(status: str) -> bool:
    return status in {AttemptStatus.COMPLETED.value, AttemptStatus.FAILED.value,
                      AttemptStatus.CANCELLED.value, AttemptStatus.INTERRUPTED.value}


@dataclass(frozen=True)
class VerificationOutcome:
    status: str
    passed: bool
    reasons: tuple[str, ...] = ()
    incomplete_reasons: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.incomplete_reasons


#: check results that are simply not a pass yet; they leave the report
#: incomplete rather than failed because no conclusion was reached.
_NON_CONCLUSIVE = ("skipped", "unknown", "pending")


def acceptance_basis(required_items: Iterable[AcceptanceItem]) -> dict[str, object]:
    """Canonical view of the acceptance items a report was computed against.

    Recomputing this later and comparing tells us whether the acceptance basis
    changed (report/approval stale) without touching the original report.
    """
    items = sorted(required_items, key=lambda i: i.item_id)
    return {"items": [i.to_dict() for i in items]}


def evaluate_verification(required_items: Iterable[AcceptanceItem],
                          checks: Iterable[CheckResult],
                          evidence_mode: str = "production", *,
                          expected_candidate_digest: str | None = None,
                          human_attested_check_ids: Iterable[str] = ()) -> VerificationOutcome:
    """All required acceptance items must have a current pass check bound to the
    right candidate/environment. zero/skipped/unknown/test-simulation never pass.
    Unknown is distinct from a false boolean.

    A declared ``human_review`` item only counts when the check was submitted
    through the trusted human entry (``human_attested_check_ids``); a machine
    actor saying "I looked" is *missing*, so the report is incomplete.
    """
    items = list(required_items)
    required = [i for i in items if i.required]
    if not required:
        return VerificationOutcome(VerificationStatus.INCOMPLETE.value, False,
                                   ("zero required acceptance items",),
                                   ("zero required acceptance items",))
    checks_by_id: dict[str, list[CheckResult]] = {}
    for c in checks:
        checks_by_id.setdefault(c.check_id, []).append(c)
    attested = set(human_attested_check_ids)

    fatal: list[str] = []
    incomplete: list[str] = []
    for item in required:
        item_checks = checks_by_id.get(item.item_id, [])
        if not item_checks:
            incomplete.append(f"missing check for {item.item_id}")
            continue
        check = item_checks[0]
        if item.evidence_type == "human_review" and item.item_id not in attested:
            incomplete.append(f"missing human check for {item.item_id}")
            continue
        if check.result != "pass":
            reason = f"{check.result} check for {item.item_id}"
            (incomplete if check.result in _NON_CONCLUSIVE else fatal).append(reason)
            continue
        if evidence_mode == "production" and check.evidence_mode == "test":
            incomplete.append(f"simulation evidence for {item.item_id}")
            continue
        if check.candidate_digest is None:
            incomplete.append(f"pass without candidate_digest for {item.item_id}")
            continue
        if (expected_candidate_digest is not None
                and check.candidate_digest != expected_candidate_digest):
            incomplete.append(f"stale candidate for {item.item_id}")
            continue

    if not fatal and not incomplete:
        return VerificationOutcome(VerificationStatus.PASSED.value, True)
    status = VerificationStatus.FAILED.value if fatal else VerificationStatus.INCOMPLETE.value
    return VerificationOutcome(status, False, tuple(fatal + incomplete), tuple(incomplete))


def approval_transition(current_status: str, decision: str, *, is_human: bool,
                        snapshot_eligible: bool) -> ProposedTransition | Rejection:
    if not is_human:
        return Rejection(current_status, decision,
                         BlockError(ErrorCode.HUMAN_IDENTITY_UNAVAILABLE.value,
                                    "machine actors cannot approve", retryable=False,
                                    category="permission",
                                    recovery_action="use a trusted human entry"))
    if current_status != ApprovalStatus.PENDING.value:
        return Rejection(current_status, decision,
                         invalid_input(f"approval is {current_status}, not pending"))
    if not snapshot_eligible:
        return Rejection(current_status, decision,
                         BlockError(ErrorCode.SNAPSHOT_CHANGED.value,
                                    "decisive inputs changed; a new request is required",
                                    category="conflict", recovery_action="re-request"))
    target = {"approved": ApprovalStatus.APPROVED.value,
              "rejected": ApprovalStatus.REJECTED.value}.get(decision)
    if target is None:
        return Rejection(current_status, decision, invalid_input(f"unknown decision {decision!r}"))
    return ProposedTransition(current_status, target, "approval.decide")


def delivery_transition(current_state: str, event: str, *,
                        external_fencing: bool) -> ProposedTransition | Rejection:
    if current_state == DeliveryState.APPLYING.value and event == "timeout":
        return ProposedTransition(current_state, DeliveryState.UNKNOWN.value, "timeout")
    if current_state == DeliveryState.UNKNOWN.value and event == "replay" and not external_fencing:
        return Rejection(current_state, event,
                         BlockError(ErrorCode.EXTERNAL_OUTCOME_UNKNOWN.value,
                                    "no external fence; do not auto-replay, reconcile only",
                                    retryable=True, category="infrastructure",
                                    recovery_action="query_effect"))
    if event not in _DELIVERY_TRANSITIONS.get(current_state, set()):
        return Rejection(current_state, event,
                         invalid_input(f"delivery {current_state} cannot {event}"))
    return ProposedTransition(current_state, event, event)


def can_terminate_task(phase: str, delivery_state: str | None) -> bool:
    if phase == TaskPhase.DELIVERING.value:
        return delivery_state in (DeliveryState.APPLIED.value, DeliveryState.FAILED.value)
    return True


def blocker_transition(current_state: str, event: str) -> bool:
    if current_state == "open":
        return event == "resolved"
    return False


def revoke_approval(current_status: str, *, is_human: bool,
                    apply_started: bool) -> ProposedTransition | Rejection:
    """pending revoke -> superseded; approved revoke before apply-start -> revoked;
    after apply-start only a cancel request, never a fake 'revoked'."""
    if not is_human:
        return Rejection(current_status, "approval.revoke",
                         BlockError(ErrorCode.HUMAN_IDENTITY_UNAVAILABLE.value,
                                    "machine actors cannot revoke", category="permission",
                                    recovery_action="use a trusted human entry"))
    if apply_started:
        return Rejection(current_status, "approval.revoke",
                         BlockError(ErrorCode.CANCEL_PENDING.value,
                                    "apply already started; only cancel/request reconciliation",
                                    category="business", recovery_action="delivery.reconcile"))
    if current_status == ApprovalStatus.PENDING.value:
        return ProposedTransition(current_status, ApprovalStatus.SUPERSEDED.value, "approval.revoke")
    if current_status == ApprovalStatus.APPROVED.value:
        return ProposedTransition(current_status, ApprovalStatus.REVOKED.value, "approval.revoke")
    return Rejection(current_status, "approval.revoke",
                     invalid_input(f"approval {current_status} cannot be revoked"))
