"""Pure flow state rules: transitions, verification, approval guard, fencing."""
from __future__ import annotations

from project_kernel.contracts.dto import AcceptanceItem, CheckResult, ObjectRef
from project_kernel.domain import delivery as rules
from project_kernel.domain import flow


def _item(item_id="i1", *, required=True, evidence_type="automated_test"):
    req = ObjectRef("p", "requirement", "r1", "rev-1")
    rec = ObjectRef("p", "recipe", "rec1", "rev-1")
    return AcceptanceItem(item_id=item_id, requirement_ref=req, recipe_ref=rec,
                          required=required, evidence_type=evidence_type, criterion="works")


def _check(item_id="i1", result="pass", evidence_mode="production"):
    rec = ObjectRef("p", "recipe", "rec1", "rev-1")
    return CheckResult(check_id=item_id, recipe_ref=rec, result=result,
                       candidate_digest="a" * 64, evidence_mode=evidence_mode)


# --- Task phase ------------------------------------------------------------

def test_canonical_task_path():
    path = [
        ("draft", "requirement.save", "designing"),
        ("designing", "dispatch.confirm", "dispatch_ready"),
        ("dispatch_ready", "attempt.start", "executing"),
        ("executing", "verification.run", "verifying"),
        ("verifying", "attempt.select", "delivery_ready"),
        ("delivery_ready", "delivery.request", "approval_pending"),
        ("approval_pending", "approval.approved", "delivering"),
        ("delivering", "task.close", "closed"),
    ]
    for current, cmd, expected in path:
        t = flow.task_transition(current, cmd)
        assert isinstance(t, flow.ProposedTransition), (current, cmd)
        assert t.to_state == expected


def test_illegal_task_transition_is_rejection():
    r = flow.task_transition("draft", "delivery.request")
    assert isinstance(r, flow.Rejection)
    assert r.error.code == "INVALID_INPUT"


def test_closed_is_terminal():
    assert flow.closed_is_terminal("closed")
    r = flow.task_transition("closed", "attempt.start")
    assert isinstance(r, flow.Rejection)


def test_new_attempt_after_failure_returns_to_executing():
    t = flow.task_transition("verifying", "attempt.start")
    assert t.to_state == "executing"
    t2 = flow.task_transition("delivery_ready", "attempt.start")
    assert t2.to_state == "executing"


def test_revoked_approval_returns_task_to_delivery_ready():
    for command in ("approval.revoked", "approval.superseded", "approval.expired"):
        assert flow.task_transition("approval_pending", command).to_state == "delivery_ready"
    assert flow.task_transition("approval_pending", "approval.approved").to_state == "delivering"


# --- Attempt ---------------------------------------------------------------

def test_attempt_transitions_and_terminal():
    assert flow.attempt_transition("planned", "starting")
    assert flow.attempt_transition("running", "unknown")
    assert flow.attempt_transition("unknown", "completed")
    assert not flow.attempt_transition("completed", "running")
    assert flow.attempt_is_terminal("failed")


# --- Verification ----------------------------------------------------------

def test_zero_required_items_never_pass():
    out = flow.evaluate_verification([], [])
    assert out.passed is False
    assert out.status == "incomplete"


def test_all_required_pass():
    out = flow.evaluate_verification([_item()], [_check()])
    assert out.passed is True
    assert out.status == "passed"
    assert out.complete


def test_skipped_unknown_fail_never_pass():
    for result in ("skipped", "unknown", "fail"):
        out = flow.evaluate_verification([_item()], [_check(result=result)])
        assert out.passed is False, result


def test_simulation_evidence_never_pass_in_production():
    out = flow.evaluate_verification([_item()], [_check(evidence_mode="test")],
                                     evidence_mode="production")
    assert out.passed is False
    assert out.status == "incomplete"


def test_missing_check_never_pass():
    out = flow.evaluate_verification([_item("i1"), _item("i2")], [_check("i1")])
    assert out.passed is False
    assert "missing" in " ".join(out.reasons)


def test_optional_item_does_not_block_but_zero_required_does():
    ok = flow.evaluate_verification([_item("i1"), _item("i2", required=False)], [_check("i1")])
    assert ok.passed is True


def test_human_review_item_without_human_submission_is_incomplete():
    out = flow.evaluate_verification([_item("doc1", evidence_type="human_review")],
                                     [_check("doc1")])
    assert out.passed is False
    assert out.status == "incomplete"
    assert "missing human check" in " ".join(out.reasons)
    attested = flow.evaluate_verification([_item("doc1", evidence_type="human_review")],
                                          [_check("doc1")],
                                          human_attested_check_ids=("doc1",))
    assert attested.passed is True


def test_stale_candidate_check_never_passes():
    out = flow.evaluate_verification([_item()], [_check()],
                                     expected_candidate_digest="b" * 64)
    assert out.passed is False
    assert out.status == "incomplete"
    assert "stale candidate" in " ".join(out.reasons)


def test_acceptance_basis_is_order_independent():
    a = flow.acceptance_basis([_item("i1"), _item("i2")])
    b = flow.acceptance_basis([_item("i2"), _item("i1")])
    assert a == b


# --- Approval (trusted human) ----------------------------------------------

def test_machine_cannot_approve():
    r = flow.approval_transition("pending", "approved", is_human=False,
                                 snapshot_eligible=True)
    assert isinstance(r, flow.Rejection)
    assert r.error.code == "HUMAN_IDENTITY_UNAVAILABLE"


def test_human_approves_pending_eligible_snapshot():
    t = flow.approval_transition("pending", "approved", is_human=True,
                                 snapshot_eligible=True)
    assert isinstance(t, flow.ProposedTransition)
    assert t.to_state == "approved"


def test_snapshot_changed_blocks_approval():
    r = flow.approval_transition("pending", "approved", is_human=True,
                                 snapshot_eligible=False)
    assert isinstance(r, flow.Rejection)
    assert r.error.code == "SNAPSHOT_CHANGED"


def test_rejected_is_not_approved():
    t = flow.approval_transition("pending", "rejected", is_human=True,
                                 snapshot_eligible=True)
    assert t.to_state == "rejected"
    # rejected never flips to approved in place; a new request is required
    r = flow.approval_transition("rejected", "approved", is_human=True,
                                 snapshot_eligible=True)
    assert isinstance(r, flow.Rejection)


def test_revoke_semantics_are_separate_from_apply_start():
    assert flow.revoke_approval("pending", is_human=True,
                                apply_started=False).to_state == "superseded"
    assert flow.revoke_approval("approved", is_human=True,
                                apply_started=False).to_state == "revoked"
    after = flow.revoke_approval("approved", is_human=True, apply_started=True)
    assert isinstance(after, flow.Rejection)
    assert after.error.code == "CANCEL_PENDING"
    machine = flow.revoke_approval("approved", is_human=False, apply_started=False)
    assert machine.error.code == "HUMAN_IDENTITY_UNAVAILABLE"
    for status in ("expired", "superseded", "rejected"):
        r = flow.revoke_approval(status, is_human=True, apply_started=False)
        assert isinstance(r, flow.Rejection), status


# --- Delivery / fencing ----------------------------------------------------

def test_claim_unclaim_before_start():
    assert flow.delivery_transition("prepared", "claimed",
                                    external_fencing=False).to_state == "claimed"
    assert flow.delivery_transition("claimed", "prepared",
                                    external_fencing=False).to_state == "prepared"


def test_unknown_delivery_cannot_auto_replay_without_fence():
    r = flow.delivery_transition("unknown", "replay", external_fencing=False)
    assert isinstance(r, flow.Rejection)
    assert r.error.code == "EXTERNAL_OUTCOME_UNKNOWN"


def test_applied_cannot_return_to_prepared():
    r = flow.delivery_transition("applied", "prepared", external_fencing=False)
    assert isinstance(r, flow.Rejection)


def test_terminate_requires_no_inflight_delivery():
    assert flow.can_terminate_task("delivering", "unknown") is False
    assert flow.can_terminate_task("delivering", "applied") is True
    assert flow.can_terminate_task("verifying", None) is True


# --- Effect / archive rules ------------------------------------------------

def test_effect_classification_matrix():
    assert rules.classify_effect(target_present=True, digest_matches=True) == "applied"
    assert rules.classify_effect(target_present=True, digest_matches=False) == "unknown"
    assert rules.classify_effect(target_present=False, digest_matches=None) == "absent_pending"
    assert rules.classify_effect(target_present=False, digest_matches=None,
                                 execution_terminal=True) == "absent_final"
    assert rules.classify_effect(target_present=False, digest_matches=None,
                                 external_fence=True) == "absent_final"
    assert rules.classify_effect(target_present=True, digest_matches=True,
                                 effect_query_failed=True) == "unknown"


def test_only_applied_or_proven_absence_releases_the_blocker():
    assert rules.is_effect_final("applied")
    assert rules.is_effect_final("absent_final")
    assert not rules.is_effect_final("absent_pending")
    assert not rules.is_effect_final("unknown")
    assert rules.reconcile_requires_terminal_evidence("absent_final", execution_terminal=False,
                                                     fence_evidence_ref=None) is False
    assert rules.reconcile_requires_terminal_evidence("absent_final", execution_terminal=True,
                                                     fence_evidence_ref=None) is True


def test_archive_overall_never_claims_complete_early():
    assert rules.archive_overall(["exports"], {}) == "export_pending"
    assert rules.archive_overall(["exports"], {"exports": "failed"}) == "export_pending"
    assert rules.archive_overall(["exports"], {"exports": "succeeded"},
                                 source_flushed=False) == "partial"
    assert rules.archive_overall(["exports"], {"exports": "succeeded"}) == "complete"
    assert rules.archive_overall(["exports", "backup"], {"exports": "succeeded"}) == "partial"


def test_decisive_projection_ignores_display_names():
    a = rules.decisive_projection("task", {"requirement_refs": [], "packet_ref": "p",
                                           "phase": "executing", "display_name": "one",
                                           "updated_at": "x"})
    b = rules.decisive_projection("task", {"requirement_refs": [], "packet_ref": "p",
                                           "phase": "delivery_ready", "display_name": "two",
                                           "updated_at": "y"})
    assert a == b
    c = rules.decisive_projection("task", {"requirement_refs": ["r2"], "packet_ref": "p"})
    assert c != a
