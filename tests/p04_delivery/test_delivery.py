"""Real bundle delivery: snapshot digest, no-overwrite, idempotent apply (AC22/AC25)."""
from __future__ import annotations

import json

from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import ObjectRef
from project_kernel.contracts.errors import KernelError

from p04_delivery.helpers import CANDIDATE, Harness, ctx, rdict

NO_DELIVERY_CAP = frozenset({"project.read", "dispatch.confirm", "approval.decide"})


def test_snapshot_body_digest_is_stable_and_shell_independent(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, body = h.freeze()
        assert sha256_digest(body) == digest
        h.approved()
        applied = h.svc.apply_delivery(ctx("ap1"), "appr-1", snapshot_id, digest)
        assert applied.status == "accepted"
        # approval/operation additions never change the frozen body digest
        assert sha256_digest(body) == digest
        assert h.svc._snapshot(snapshot_id)["digest"] == digest
        assert "approval" not in body
        assert "operation_id" not in body
        assert body["candidate_digest"] == CANDIDATE
    finally:
        h.close()


def test_freeze_rejects_a_body_that_violates_the_frozen_schema(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        body = h.snapshot_body()
        body.pop("verification_refs")
        rejected = h.svc.freeze_snapshot(ctx("f-bad"), "snap-bad", body)
        assert rejected.status == "rejected"
        assert rejected.error.code == "INVALID_INPUT"
        assert h.svc._snapshot("snap-bad") is None
    finally:
        h.close()


def test_full_loop_writes_a_real_bundle_and_retry_is_idempotent(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        applied = h.svc.apply_delivery(ctx("ap1"), approval_id, "snap-1", digest)
        assert applied.status == "accepted"
        assert applied.operation_id is not None

        operation = h.operation(applied.operation_id)
        assert operation["status"] == "applied"
        assert operation["effect_status"] == "applied"
        assert operation["sink_receipt"]["state"] == "succeeded"
        assert operation["epoch"] == 1
        assert operation["task_id"] == h.task_ref.object_id

        target = tmp_path / "exports" / applied.operation_id
        bundle = target / "artifacts" / h.artifact.sha256
        assert bundle.read_bytes() == b"deliverable content"
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["snapshot_digest"] == digest
        assert h.task_phase() == "delivering"

        # the same idempotency key returns the original receipt / operation
        retry = h.svc.apply_delivery(ctx("ap1"), approval_id, "snap-1", digest)
        assert retry.command_id == applied.command_id
        assert retry.operation_id == applied.operation_id
        assert h.svc._delivery_heads() == [applied.operation_id]
    finally:
        h.close()


def test_existing_target_with_another_digest_is_never_overwritten(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        operation_id = Harness.operation_id_for("ap-x")
        target = tmp_path / "exports" / operation_id
        target.mkdir(parents=True)
        (target / "manifest.json").write_text(json.dumps({"foreign": "manifest"}) + "\n",
                                              encoding="utf-8")

        applied = h.svc.apply_delivery(ctx("ap-x"), approval_id, "snap-1", digest)
        assert applied.status == "accepted"
        operation = h.operation(operation_id)
        # content differs from the pinned digest: unknown, never overwritten
        assert operation["status"] == "unknown"
        assert operation["effect_status"] == "unknown"
        assert json.loads((target / "manifest.json").read_text(encoding="utf-8")) == {
            "foreign": "manifest"}
        assert not (target / "artifacts").exists()
    finally:
        h.close()


def test_apply_requires_an_approved_approval(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        snapshot_id, digest, _ = h.freeze()
        h.svc.request_approval(ctx("req1"), "appr-1", snapshot_id, digest)
        rejected=h.svc.apply_delivery(ctx("ap1"), "appr-1", snapshot_id, digest)
        assert rejected.status=="rejected"
        assert rejected.error.code=="APPROVAL_INVALID"
        assert h.svc._delivery_heads() == []
    finally:
        h.close()


def test_apply_requires_the_delivery_capability(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        denied = h.svc.claim_delivery(ctx("cl-nocap", principal="tool-1", caps=NO_DELIVERY_CAP),
                                      approval_id, digest)
        assert denied.status == "rejected"
        assert denied.error.code == "PERMISSION_DENIED"
        assert h.svc._delivery_heads() == []
    finally:
        h.close()


def test_claim_then_apply_start_binds_the_operation(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        assert h.operation(operation_id)["status"] == "claimed"
        approval, _ = h.svc._head_payload("approval", approval_id)
        assert approval["operation_id"] == operation_id
        # one approval can only ever be bound to one operation
        second = h.svc.claim_delivery(ctx("cl2"), approval_id, digest)
        assert second.status == "rejected"
        assert second.error.code == "APPROVAL_INVALID"

        started = h.svc.apply_start_delivery(ctx("as1"), operation_id)
        assert started.status == "accepted"
        assert h.operation(operation_id)["status"] == "applying"
        approval, _ = h.svc._head_payload("approval", approval_id)
        assert approval["apply_started"] is True
        assert h.task_phase() == "delivering"
    finally:
        h.close()


def test_claim_refuses_when_decisive_inputs_moved(tmp_path):
    from p04_delivery.helpers import patch_object
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        patch_object(h.store, "requirement", "req-1", {"source_text": "changed"}, "req-move")
        blocked = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        assert blocked.status == "rejected"
        assert blocked.error.code == "SNAPSHOT_CHANGED"
        assert h.svc._delivery_heads() == []
    finally:
        h.close()


def test_bundle_manifest_body_references_snapshot_and_operation(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, snapshot_id, digest = h.applied()
        h.svc.task_close(ctx("c1"), h.task_ref, operation)
        status = h.svc.archive_status_for_task(h.task_ref.object_id)
        manifest_ref = ObjectRef.from_dict(status["manifest_ref"])
        body = h.store.get_revision(manifest_ref)["payload"]
        assert manifest_ref.object_id == f"archive-{operation.object_id}"
        assert body["snapshot_digest"] == digest
        assert body["delivery_operation_refs"] == [operation.object_id]
        assert body["required_sinks"] == ["exports"]
        assert status["manifest_digest"] == sha256_digest(body)
        assert rdict("delivery_target", "dt1") == h.snapshot_body()["delivery"]["target_ref"]
    finally:
        h.close()
