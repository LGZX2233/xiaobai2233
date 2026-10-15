"""Approval request/decide/revoke: trusted human only, digest-bound (AC19-AC21)."""
from __future__ import annotations

from project_kernel.contracts.errors import KernelError

from p04_delivery.helpers import CANDIDATE, Harness, ctx, patch_object, rdict

NO_APPROVAL_CAP = frozenset({"project.read", "dispatch.confirm", "delivery.apply",
                             "verification.review"})


def _expired() -> str:
    return "2000-01-01T00:00:00Z"


def test_passed_verification_reaches_delivery_ready_then_request_never_auto_approves(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        assert h.task_phase() == "delivery_ready"
        snapshot_id, digest, body = h.freeze()
        requested = h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        assert requested.status == "committed"
        assert h.svc._head_status("approval", "appr-1") == "pending"
        assert h.task_phase() == "approval_pending"
        stored = h.svc._snapshot(snapshot_id)
        assert stored["digest"] == digest
        # requesting is not approving: the operation is not bound and nothing applied
        approval, _ = h.svc._head_payload("approval", "appr-1")
        assert approval["operation_id"] is None
        assert h.svc._delivery_heads() == []
    finally:
        h.close()


def test_request_approval_requires_delivery_ready_task(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        patch_object(h.store,"task",h.task_ref.object_id,{"phase":"verifying"},"phase-change")
        assert h.task_phase() == "verifying"
        rejected = h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        assert rejected.status == "rejected"
        assert rejected.error.code == "INVALID_INPUT"
        assert h.svc._head_status("approval", "appr-1") is None
    finally:
        h.close()


def test_machine_actor_cannot_approve_even_with_the_capability(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        # a fresh pending approval for a second snapshot, decided by a machine actor
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        machine = h.svc.decide_approval(ctx("m1", principal="agent-1"), "appr-1", "approved",
                                        digest, is_human=False, reason="auto")
        assert machine.status == "rejected"
        assert machine.error.code == "HUMAN_IDENTITY_UNAVAILABLE"
        # the machine principal does hold approval.decide: identity is the gate,
        # not the capability alone
        assert ctx("m1", principal="agent-1").scope.has("approval.decide")
        assert h.svc._head_status("approval", "appr-1") == "pending"
        assert h.task_phase() == "approval_pending"
    finally:
        h.close()


def test_human_without_approval_capability_is_denied(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        denied = h.svc.decide_approval(ctx("d1", principal="human-2", caps=NO_APPROVAL_CAP),
                                       "appr-1", "approved", digest, is_human=True,
                                       reason="let me in")
        assert denied.status == "rejected"
        assert denied.error.code == "PERMISSION_DENIED"
        assert h.svc._head_status("approval", "appr-1") == "pending"
    finally:
        h.close()


def test_decide_is_bound_to_the_snapshot_digest(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        wrong = h.svc.decide_approval(ctx("dec-wrong"), "appr-1", "approved", "a" * 64,
                                      is_human=True, reason="wrong digest")
        assert wrong.status == "rejected"
        assert wrong.error.code == "APPROVAL_INVALID"
    finally:
        h.close()


def test_unrelated_display_name_change_does_not_invalidate(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        patch_object(h.store, "task", h.task_ref.object_id, {"display_name": "renamed"}, "rn1")
        ok = h.svc.decide_approval(ctx("dec-rename"), "appr-1", "approved", digest, is_human=True,
                                   reason="unchanged inputs")
        assert ok.status == "committed", ok.error
        assert h.svc._head_status("approval", "appr-1") == "approved"
    finally:
        h.close()


def test_decisive_requirement_change_supersedes_the_pending_approval(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        # the requirement text is a decisive input of the approved snapshot
        patch_object(h.store, "requirement", "req-1",
                     {"source_text": "materially different"}, "req-change")
        stale = h.svc.decide_approval(ctx("dec-stale"), "appr-1", "approved", digest,
                                      is_human=True, reason="stale")
        assert stale.status == "rejected"
        assert stale.error.code == "SNAPSHOT_CHANGED"
        assert h.svc._head_status("approval", "appr-1") == "superseded"
        # Supersession preserves the immutable snapshot content.
        assert h.svc._snapshot(snapshot_id)["digest"] == digest
    finally:
        h.close()


def test_stale_verification_supersedes_the_pending_approval(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        # the candidate content moves on: the report is stale, so any approval that
        # still references it is superseded (visible, original report kept)
        patch_object(h.store, "candidate_manifest", "cand-1",
                     {"candidate_digest": "e" * 64}, "cand-change")
        assessed = h.svc.check_validity(ctx("cv-stale"), h.report_ref)
        assert assessed.status == "committed"
        assert h.report()["validity"] == "stale"
        assert h.svc._head_status("approval", "appr-1") == "superseded"
        assert h.task_phase() == "delivery_ready"
        stale = h.svc.decide_approval(ctx("dec-stale"), "appr-1", "approved", digest,
                                      is_human=True, reason="stale evidence")
        assert stale.status == "rejected"
        assert stale.error.code == "SNAPSHOT_CHANGED"
    finally:
        h.close()


def test_expiry_is_visible_and_blocks_approval(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest, expires_at=_expired())
        try:
            h.svc.decide_approval(ctx("dec-late"), "appr-1", "approved", digest, is_human=True,
                                  reason="late")
            raise AssertionError("expected APPROVAL_INVALID")
        except KernelError as exc:
            assert exc.error.code == "APPROVAL_INVALID"
        assert h.svc._head_status("approval", "appr-1") == "expired"
        assert h.task_phase() == "delivery_ready"
        revoked = h.svc.approval_revoke(ctx("rv1"), "appr-1", digest, is_human=True,
                                        reason="too late")
        assert revoked.status == "rejected"
        assert revoked.error.code == "INVALID_INPUT"
    finally:
        h.close()


def test_revoke_pending_is_superseded_and_returns_task(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        assert h.task_phase() == "approval_pending"
        machine = h.svc.approval_revoke(ctx("rv0"), "appr-1", digest, is_human=False,
                                        reason="auto")
        assert machine.status == "rejected"
        assert machine.error.code == "HUMAN_IDENTITY_UNAVAILABLE"
        wrong_digest = h.svc.approval_revoke(ctx("rv1"), "appr-1", "a" * 64, is_human=True,
                                             reason="wrong")
        assert wrong_digest.status == "rejected"
        assert wrong_digest.error.code == "SNAPSHOT_CHANGED"
        no_reason = h.svc.approval_revoke(ctx("rv2"), "appr-1", digest, is_human=True)
        assert no_reason.status == "rejected"
        assert no_reason.error.code == "INVALID_INPUT"
        ok = h.svc.approval_revoke(ctx("rv3"), "appr-1", digest, is_human=True,
                                   reason="wrong target selected")
        assert ok.status == "committed"
        payload, _ = h.svc._head_payload("approval", "appr-1")
        assert payload["status"] == "superseded"
        assert payload["revoke_reason"] == "wrong target selected"
        assert payload["revoked_by"] == "human-1"
        assert h.task_phase() == "delivery_ready"
    finally:
        h.close()


def test_revoke_approved_before_apply_start_is_revoked(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        assert h.task_phase() == "delivering"
        revoked = h.svc.approval_revoke(ctx("rv1"), approval_id, digest, is_human=True,
                                        reason="changed my mind")
        assert revoked.status == "committed"
        assert h.svc._head_status("approval", approval_id) == "revoked"
        assert h.task_phase() == "delivery_ready"
        # a revoked approval can never be applied
        rejected=h.svc.apply_delivery(ctx("ap1"), approval_id, "snap-1", digest)
        assert rejected.status=="rejected"
        assert rejected.error.code=="APPROVAL_INVALID"
    finally:
        h.close()


def test_revoke_after_apply_start_only_requests_cancellation(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        started = h.svc.apply_start_delivery(ctx("as1"), operation_id)
        assert started.status == "accepted"
        late = h.svc.approval_revoke(ctx("rv1"), approval_id, digest, is_human=True,
                                     reason="stop it")
        assert late.status == "rejected"
        assert late.error.code == "CANCEL_PENDING"
        payload, _ = h.svc._head_payload("approval", approval_id)
        assert payload["status"] == "approved"
        assert payload["apply_started"] is True
        assert h.svc._head_status("delivery", operation_id) == "applying"
    finally:
        h.close()


def test_same_snapshot_request_returns_the_active_approval(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        first = h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        second = h.svc.request_approval(ctx("req2"), "appr-2", snapshot_id, digest)
        assert second.status == "committed"
        assert second.object_refs[0].object_id == first.object_refs[0].object_id
        assert h.svc._head_status("approval", "appr-2") is None
    finally:
        h.close()


def test_snapshot_body_digest_is_shell_independent(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, body = h.freeze()
        h.approved(request_key="req1", decide_key="dec-shell")
        assert h.svc._snapshot(snapshot_id)["digest"] == digest
        from project_kernel.contracts import sha256_digest
        assert sha256_digest(body) == digest
        assert CANDIDATE == body["candidate_digest"]
        assert rdict("delivery_target", "dt1") == body["delivery"]["target_ref"]
    finally:
        h.close()
