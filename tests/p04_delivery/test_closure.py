"""task.close / task.terminate closure: archive linkage and outbox (design 03 §8)."""
from __future__ import annotations
import pytest
from project_kernel.contracts.errors import KernelError

from p04_delivery.helpers import Harness, ctx, patch_object, rdict, seed_revision


def _outbox(store):
    return store.conn.execute(
        "SELECT consumer, effect_kind, state FROM outbox ORDER BY outbox_id").fetchall()


def test_close_requires_an_applied_operation(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        blocked = h.svc.task_close(ctx("c1"), h.task_ref,
                                   {"project_id": "proj-a", "object_type": "delivery",
                                    "object_id": operation_id, "revision_id": "rev-1"})
        assert blocked.status == "rejected"
        assert blocked.error.code == "APPROVAL_INVALID"
        assert h.task_phase() == "delivering"
    finally:
        h.close()


def test_close_marks_delivered_and_links_the_archive(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, digest = h.applied()
        closed = h.svc.task_close(ctx("c1"), h.task_ref, operation)
        assert closed.status == "committed"
        task = h.task_payload()
        assert task["phase"] == "closed"
        assert task["terminal_outcome"] == "delivered"
        assert task["applied_operation_ref"]["object_id"] == operation.object_id
        assert task["archive_overall"] == "export_pending"

        status = h.svc.archive_status_for_task(h.task_ref.object_id)
        assert status["overall"] == "export_pending"
        assert status["sink_states"] == {}
        assert status["required_sinks"] == ["exports"]
        # a durable archive outbox effect was enqueued for the real sink worker
        assert _outbox(h.store) == [("archive", "archive.export", "pending")]

        # until the sink really succeeds the manifest must not claim complete
        h.svc.record_sink_result(ctx("s1"), h.task_ref.object_id, "exports", "succeeded",
                                 digest=status["manifest_digest"], locator="exports", verified=True)
        status = h.svc.archive_status_for_task(h.task_ref.object_id)
        assert status["overall"] == "complete"
        assert status["sink_states"] == {"exports": "succeeded"}
    finally:
        h.close()


def test_archive_never_claims_complete_without_the_source_flush(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        h.svc.task_close(ctx("c1"), h.task_ref, operation, source_flushed=False)
        h.svc.record_sink_result(ctx("s1"), h.task_ref.object_id, "exports", "succeeded",
                                 source_flushed=False, verified=True,
                                 digest=h.svc.archive_status_for_task(h.task_ref.object_id)["manifest_digest"])
        status = h.svc.archive_status_for_task(h.task_ref.object_id)
        assert status["overall"] == "partial"
    finally:
        h.close()


def test_close_twice_is_rejected(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        assert h.svc.task_close(ctx("c1"), h.task_ref, operation).status == "committed"
        again = h.svc.task_close(ctx("c2"), h.task_ref, operation)
        assert again.status == "rejected"
        assert again.error.code == "INVALID_INPUT"
    finally:
        h.close()


def test_close_refuses_when_the_primary_evidence_is_no_longer_accepted(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        # the human review is withdrawn: the report no longer passes
        failed = h.svc.record_review(ctx("rv1"), h.report_ref, "i1",
                                     h.snapshot_body()["candidate_digest"], "fail",
                                     [rdict("evidence", "e1")], "regression found",
                                     is_human=True)
        assert failed.status == "committed"
        assert h.report()["passed"] is False
        blocked = h.svc.task_close(ctx("c1"), h.task_ref, operation)
        assert blocked.status == "rejected"
        assert blocked.error.code == "VERIFICATION_FAILED"
        assert h.task_phase() == "delivering"
    finally:
        h.close()


def test_terminate_is_blocked_while_a_delivery_is_unknown(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        with pytest.raises(KernelError) as caught:
            h.svc.task_terminate(ctx("tm1"), h.task_ref, "terminated", "give up")
        assert caught.value.error.code == "EXTERNAL_OUTCOME_UNKNOWN"
        assert h.store.get_receipt("human-1","tm1") is None
        assert h.task_phase() == "delivering"
        assert h.operation(operation_id)["status"] == "applying"
    finally:
        h.close()


def test_terminate_after_proven_no_effect_preserves_failures(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        h.svc.delivery_reconcile(ctx("rc1"), operation_id,
                                 effect_receipt={"operation_id": operation_id,
                                                 "status": "absent_final",
                                                 "execution_terminal": True})
        assert h.operation(operation_id)["status"] == "failed"
        terminated = h.svc.task_terminate(ctx("tm1"), h.task_ref, "terminated",
                                          "provider never applied anything")
        assert terminated.status == "committed"
        task = h.task_payload()
        assert task["phase"] == "closed"
        assert task["terminal_outcome"] == "terminated"
        assert task["terminate_reason"] == "provider never applied anything"
        assert task["settled_deliveries"] == [{"operation_id": operation_id,
                                               "status": "failed"}]
        assert task["unclaimed_operations"] == []
    finally:
        h.close()


def test_terminate_unclaims_a_claimed_operation_and_blocks_apply_start(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        terminated = h.svc.task_terminate(ctx("tm1"), h.task_ref, "cancelled", "abandoned")
        assert terminated.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "prepared"
        assert operation["apply_blocked"] is True
        assert h.task_payload()["unclaimed_operations"] == [operation_id]
        blocked = h.svc.apply_start_delivery(ctx("as1"), operation_id)
        assert blocked.status == "rejected"
        assert blocked.error.code == "CANCEL_PENDING"
    finally:
        h.close()


def test_terminate_ignores_the_callers_unsettled_self_report(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        h.svc.apply_start_delivery(ctx("as1"), claim.object_refs[0].object_id)
        # claiming "nothing is in flight" must not override the real state
        with pytest.raises(KernelError) as caught:
            h.svc.task_terminate(ctx("tm1"), h.task_ref, "terminated", "trust me",unsettled_refs=[])
        assert caught.value.error.code == "EXTERNAL_OUTCOME_UNKNOWN"
    finally:
        h.close()


def test_terminate_requires_settled_attempts(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_verifying()
        seed_revision(h.store, "attempt", "attempt-live",
                      {"attempt_id": "attempt-live", "task_ref": h.task_ref.to_dict(),
                       "status": "running"}, "seed-live")
        blocked = h.svc.task_terminate(ctx("tm1"), h.task_ref, "terminated", "stop")
        assert blocked.status == "rejected"
        assert blocked.error.code == "REQUIRED_FACT_UNKNOWN"
        assert h.task_phase() != "closed"
    finally:
        h.close()


def test_terminate_requires_a_reason_and_a_known_outcome(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        no_reason = h.svc.task_terminate(ctx("tm1"), h.task_ref, "terminated", "")
        assert no_reason.status == "rejected"
        assert no_reason.error.code == "INVALID_INPUT"
        bad_outcome = h.svc.task_terminate(ctx("tm2"), h.task_ref, "delivered", "nope")
        assert bad_outcome.status == "rejected"
        assert bad_outcome.error.code == "INVALID_INPUT"
    finally:
        h.close()


def test_closed_task_cannot_be_terminated_or_reopened(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        h.svc.task_close(ctx("c1"), h.task_ref, operation)
        terminated = h.svc.task_terminate(ctx("tm1"), h.task_ref, "terminated", "reopen")
        assert terminated.status == "rejected"
        assert terminated.error.code == "INVALID_INPUT"
        assert h.task_payload()["terminal_outcome"] == "delivered"
    finally:
        h.close()


def test_record_sink_result_rejects_an_unknown_sink(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        h.svc.task_close(ctx("c1"), h.task_ref, operation)
        bad = h.svc.record_sink_result(ctx("s1"), h.task_ref.object_id, "nowhere", "succeeded")
        assert bad.status == "rejected"
        assert bad.error.code == "INVALID_INPUT"
        unknown = h.svc.record_sink_result(ctx("s2"), "no-such-task", "exports", "succeeded")
        assert unknown.status == "rejected"
        assert unknown.error.code == "REFERENCE_NOT_FOUND"
    finally:
        h.close()


def test_close_requires_the_delivery_capability(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        denied = h.svc.task_close(ctx("c1", principal="tool-3",
                                      caps=frozenset({"project.read", "dispatch.confirm"})),
                                  h.task_ref, operation)
        assert denied.status == "rejected"
        assert denied.error.code == "PERMISSION_DENIED"
        assert h.task_phase() == "delivering"
    finally:
        h.close()


def test_terminate_requires_the_dispatch_capability(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        denied = h.svc.task_terminate(ctx("tm1", principal="tool-4",
                                          caps=frozenset({"project.read", "delivery.apply"})),
                                      h.task_ref, "terminated", "no permission")
        assert denied.status == "rejected"
        assert denied.error.code == "PERMISSION_DENIED"
    finally:
        h.close()


@pytest.mark.parametrize("valid_digest,verified", [(False, True), (True, False), (True, "true")])
def test_sink_callback_rejects_unverified_or_wrong_manifest_success(tmp_path, valid_digest, verified):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        h.svc.task_close(ctx("close"), h.task_ref, operation)
        status = h.svc.archive_status_for_task(h.task_ref.object_id)
        receipt = h.svc.record_sink_result(ctx("sink"), h.task_ref.object_id, "exports", "succeeded",
            digest=status["manifest_digest"] if valid_digest else "b" * 64, verified=verified)
        assert receipt.status == "rejected"
        assert h.svc.archive_status_for_task(h.task_ref.object_id)["overall"] == "export_pending"
    finally:
        h.close()
