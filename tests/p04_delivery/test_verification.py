"""verification.run persistence + validity/report completeness (AC18)."""
from __future__ import annotations

from project_kernel.contracts.dto import CheckResult, ObjectRef

from p04_delivery.helpers import (
    CANDIDATE,
    Harness,
    acceptance_item,
    ctx,
    oref,
    rdict,
    seed_revision,
)


def _pass(item_id: str) -> CheckResult:
    return CheckResult(check_id=item_id,
                       recipe_ref=ObjectRef.from_dict(rdict("recipe", f"recipe-{item_id}")),
                       candidate_digest=CANDIDATE, result="pass", evidence_mode="test")


def _report(harness: Harness) -> dict:
    return harness.report()


def test_zero_required_items_report_incomplete_and_persisted(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_attempt()
        # no applicable acceptance item at all: refuse rather than silently pass
        empty = h.svc.verification_run(ctx("v0"), h.attempt_ref, h.candidate, [], [],
                                       evidence_mode="test")
        assert empty.status == "rejected"
        assert empty.error.code == "REQUIRED_FACT_UNKNOWN"
        # items declared but none required: a persisted report that is incomplete
        optional = [acceptance_item("i1", required=False)]
        report = h.svc.verification_run(ctx("v0b"), h.attempt_ref, h.candidate, optional, [],
                                        evidence_mode="test")
        assert report.status == "committed"
        stored = h.store.get_revision(report.object_refs[0])["payload"]
        assert stored["passed"] is False
        assert stored["result"] == "incomplete"
        assert stored["complete"] is False
        assert stored["validity"] == "current"
        assert "zero required acceptance items" in stored["reasons"]
    finally:
        h.close()


def test_skipped_and_unknown_and_simulation_never_pass(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_attempt()
        item = [acceptance_item("i1")]
        for result in ("skipped", "unknown", "fail"):
            check = CheckResult(check_id="i1",
                                recipe_ref=ObjectRef.from_dict(rdict("recipe", "recipe-i1")),
                                candidate_digest=CANDIDATE, result=result,
                                evidence_mode="test")
            receipt = h.svc.verification_run(ctx(f"v-{result}"), h.attempt_ref, h.candidate,
                                             item, [check], evidence_mode="test")
            assert h.store.get_revision(receipt.object_refs[0])["payload"]["passed"] is False
        sim = CheckResult(check_id="i1",
                          recipe_ref=ObjectRef.from_dict(rdict("recipe", "recipe-i1")),
                          candidate_digest=CANDIDATE, result="pass", evidence_mode="test")
        receipt = h.svc.verification_run(ctx("v-sim"), h.attempt_ref, h.candidate, item, [sim],
                                        evidence_mode="production")
        stored = h.store.get_revision(receipt.object_refs[0])["payload"]
        assert stored["passed"] is False
        assert "simulation" in " ".join(stored["reasons"])
    finally:
        h.close()


def test_stale_candidate_manifest_cannot_pass(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_attempt()
        stale_ref = oref("candidate_manifest", "cand-old", "rev-1")
        seed_revision(h.store, "candidate_manifest", "cand-old",
                      {"candidate_digest": "c" * 64}, "seedcand")
        # a newer revision of the same object supersedes the pinned reference
        seed_revision(h.store, "candidate_manifest", "cand-old",
                      {"candidate_digest": "d" * 64}, "seedcand2")
        receipt = h.svc.verification_run(ctx("v1"), h.attempt_ref, stale_ref,
                                        [acceptance_item("i1")],
                                        [CheckResult(check_id="i1",
                                                     recipe_ref=ObjectRef.from_dict(
                                                         rdict("recipe", "recipe-i1")),
                                                     candidate_digest="c" * 64,
                                                     result="pass", evidence_mode="test")],
                                        evidence_mode="test")
        stored = h.store.get_revision(receipt.object_refs[0])["payload"]
        assert stored["passed"] is False
        assert stored["result"] == "incomplete"
        assert "stale candidate manifest" in stored["reasons"]
    finally:
        h.close()


def test_human_review_missing_is_incomplete_and_record_review_does_not_overwrite(tmp_path):
    h = Harness(tmp_path)
    try:
        items = [acceptance_item("i1"),
                 acceptance_item("doc1", evidence_type="human_review")]
        # a machine-provided "pass" for the declared human item does not count
        checks = [_pass("i1"), _pass("doc1")]
        info = h.to_verifying(items=items, checks=checks)
        report = _report(h)
        assert report["passed"] is False
        assert report["result"] == "incomplete"
        assert "missing human check for doc1" in report["reasons"]
        first_revision = info["report_ref"].revision_id

        machine = h.svc.record_review(ctx("rv1"), h.report_ref, "doc1", CANDIDATE, "pass",
                                      [rdict("evidence", "e1")], "looks fine", is_human=False)
        assert machine.status == "rejected"
        assert machine.error.code == "HUMAN_IDENTITY_UNAVAILABLE"

        human = h.svc.record_review(ctx("rv2"), h.report_ref, "doc1", CANDIDATE, "pass",
                                    [rdict("evidence", "e1")], "reviewed the document",
                                    is_human=True)
        assert human.status == "committed"
        assert human.object_refs[0].revision_id != first_revision
        updated = _report(h)
        assert updated["passed"] is True
        assert updated["review"]["reviewer"] == "human-1"
        # the earlier report revision is untouched
        old = h.store.get_revision(oref("verification", h.report_ref.object_id,
                                        first_revision))["payload"]
        assert old["passed"] is False
        assert old["result"] == "incomplete"
    finally:
        h.close()


def test_record_review_requires_matching_candidate_and_evidence(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_verifying(items=[acceptance_item("i1")])
        bad_candidate = h.svc.record_review(ctx("rv1"), h.report_ref, "i1", "f" * 64, "pass",
                                            [rdict("evidence", "e1")], "nope", is_human=True)
        assert bad_candidate.status == "rejected"
        assert bad_candidate.error.code == "EVIDENCE_STALE"
        no_evidence = h.svc.record_review(ctx("rv2"), h.report_ref, "i1", CANDIDATE, "pass",
                                          [], "nope", is_human=True)
        assert no_evidence.status == "rejected"
        assert no_evidence.error.code == "INVALID_INPUT"
        unknown_item = h.svc.record_review(ctx("rv3"), h.report_ref, "nope", CANDIDATE, "pass",
                                           [rdict("evidence", "e1")], "nope", is_human=True)
        assert unknown_item.status == "rejected"
        assert unknown_item.error.code == "REFERENCE_NOT_FOUND"
    finally:
        h.close()


def test_acceptance_refs_are_resolved_and_missing_refs_rejected(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_attempt()
        items = [acceptance_item("i1"), acceptance_item("i2")]
        acceptance = seed_revision(h.store, "acceptance", "acc-ref",
                                   {"acceptance_items": items}, "seed-acc")
        checks = [_pass("i1"), _pass("i2")]
        receipt = h.svc.verification_run(ctx("v1"), h.attempt_ref, h.candidate,
                                         acceptance_refs=[acceptance], check_results=checks,
                                         evidence_mode="test")
        stored = h.store.get_revision(receipt.object_refs[0])["payload"]
        assert stored["passed"] is True
        assert stored["acceptance_refs"] == [acceptance.to_dict()]

        missing = h.svc.verification_run(ctx("v2"), h.attempt_ref, h.candidate,
                                         acceptance_refs=[rdict("acceptance", "nope")],
                                         check_results=[], evidence_mode="test")
        assert missing.status == "rejected"
        assert missing.error.code == "REFERENCE_NOT_FOUND"
    finally:
        h.close()


def test_check_validity_marks_stale_on_acceptance_change_and_supersedes_approval(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_attempt()
        items = [acceptance_item("i1")]
        acceptance = h.acceptance_ref
        checks = [_pass("i1")]
        receipt = h.svc.verification_run(ctx("v1"), h.attempt_ref, h.candidate,
                                         acceptance_refs=[acceptance], check_results=checks,
                                         evidence_mode="test")
        report_ref = receipt.object_refs[0]
        h.report_ref = report_ref
        assert h.store.get_revision(report_ref)["payload"]["passed"] is True

        same = h.svc.check_validity(ctx("cv1"), report_ref)
        assert same.status == "committed"
        assert same.object_refs == ()
        assert h.svc._head_payload("verification", report_ref.object_id)[0]["validity"] == "current"

        # the decisive acceptance basis changes -> report stale, approval superseded
        h.select()
        approval_id, digest = h.approved()
        assert h.svc._head_status("approval", approval_id) == "approved"
        seed_revision(h.store, "acceptance", h.acceptance_ref.object_id,
                      {"acceptance_items": items + [acceptance_item("i2")]}, "seed-acc2")
        changed = h.svc.check_validity(ctx("cv2"), report_ref)
        assert changed.status == "committed"
        assert changed.object_refs != ()
        stored = h.svc._head_payload("verification", report_ref.object_id)[0]
        assert stored["validity"] == "stale"
        assert "acceptance basis changed" in stored["validity_reasons"]
        assert h.svc._head_status("approval", approval_id) == "superseded"
        assert h.task_phase() == "delivery_ready"
    finally:
        h.close()
