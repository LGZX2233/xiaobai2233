"""Crash / reconcile / epoch paths: never blindly replay an external write (AC23/AC24)."""
from __future__ import annotations

import pytest
from project_kernel.contracts.dto import ArtifactRef, EffectReceipt
from project_kernel.contracts.errors import KernelError
from project_kernel.evidence.archive import ArchiveManifest

from p04_delivery.helpers import Harness, ctx, patch_object


def _manifest(h: Harness, operation_id: str, digest: str) -> ArchiveManifest:
    artifact = ArtifactRef(h.artifact.artifact_id, h.artifact.sha256, h.artifact.size_bytes,
                           h.artifact.media_type, h.artifact.required)
    return ArchiveManifest(manifest_id=operation_id, snapshot_digest=digest,
                           delivery_operation_refs=(operation_id,), artifacts=(artifact,),
                           required_sinks=("exports",))


def test_crash_before_apply_start_keeps_claim_then_unclaims_after_lease_expiry(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        assert h.operation(operation_id)["status"] == "claimed"

        same = h.svc.delivery_reconcile(ctx("rc1"), operation_id,
                                        effect_receipt={"operation_id": operation_id,
                                                        "status": "absent_pending"})
        assert same.status == "committed"
        assert h.operation(operation_id)["status"] == "claimed"

        patch_object(h.store, "delivery", operation_id,
                     {"lease_until": "2000-01-01T00:00:00Z"}, "lease-expire")
        unclaimed = h.svc.delivery_reconcile(ctx("rc2"), operation_id,
                                            effect_receipt={"operation_id": operation_id,
                                                            "status": "absent_pending"})
        assert unclaimed.status == "committed"
        assert h.operation(operation_id)["status"] == "prepared"
        # still exactly one operation: reconcile never replays
        assert h.svc._delivery_heads() == [operation_id]
    finally:
        h.close()


def test_crash_after_apply_start_is_unknown_until_a_real_effect_is_queried(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        assert h.operation(operation_id)["status"] == "applying"

        unknown = h.svc.delivery_reconcile(ctx("rc1"), operation_id)
        assert unknown.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "unknown"
        # the target is simply absent and nothing proves the write never happened
        assert operation["effect_status"] == "absent_pending"
        assert operation["execution_terminal"] is False
        assert h.svc._delivery_heads() == [operation_id]
    finally:
        h.close()


def test_effect_present_with_pinned_digest_recovers_applied(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        # the external write landed but the receipt was lost (crash before settle)
        receipt = h.exporter.export(_manifest(h, operation_id, digest), "exports")
        assert receipt.state == "succeeded"

        recovered = h.svc.delivery_reconcile(ctx("rc1"), operation_id)
        assert recovered.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "applied"
        assert operation["effect_status"] == "applied"
        assert operation["manifest_digest"] == _manifest(h, operation_id, digest).digest()
        assert operation["reconciled"] is True
    finally:
        h.close()


def test_absent_final_needs_terminal_evidence(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)

        # "the file is not there right now" is not proof of no effect
        bare = h.svc.delivery_reconcile(ctx("rc1"), operation_id,
                                        effect_receipt={"operation_id": operation_id,
                                                        "status": "absent_final"})
        assert bare.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "unknown"
        assert operation["effect_status"] == "unknown"

        terminal = h.svc.delivery_reconcile(
            ctx("rc2"), operation_id,
            effect_receipt={"operation_id": operation_id, "status": "absent_final",
                            "execution_terminal": True})
        assert terminal.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "failed"
        assert operation["effect_status"] == "absent_final"
        assert operation["execution_terminal"] is True
    finally:
        h.close()


def test_external_fence_can_prove_absent_final(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        from p04_delivery.helpers import seed_revision
        fence_ref = seed_revision(h.store, "fence", "f1", {"operation_id": operation_id}, "fence")
        fenced = h.svc.delivery_reconcile(
            ctx("rc1"), operation_id,
            effect_receipt={"operation_id": operation_id, "status": "absent_final",
                            "execution_terminal": False,
                            "fence_evidence_ref": fence_ref.to_dict()})
        assert fenced.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "failed"
        assert operation["fence_evidence_ref"]["object_id"] == "f1"
    finally:
        h.close()


def test_late_old_epoch_result_is_audited_and_never_applied(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)

        late = h.svc.delivery_reconcile(ctx("rc1"), operation_id,
                                        effect_receipt={"operation_id": operation_id,
                                                        "status": "applied"},
                                        epoch=0)
        assert late.status == "committed"
        assert late.object_refs == ()
        assert h.operation(operation_id)["status"] == "applying"
        rows = h.store.conn.execute(
            "SELECT event_type FROM audit_event WHERE event_type='delivery.stale_epoch_result'"
        ).fetchall()
        assert rows
    finally:
        h.close()


@pytest.mark.parametrize("receipt", [
    {"status": "applied"},
    {"operation_id": "another-operation", "status": "applied"},
])
def test_reconcile_rejects_missing_or_foreign_operation_identity(tmp_path, receipt):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        with pytest.raises(KernelError):
            h.svc.delivery_reconcile(ctx("rc1"), operation_id, effect_receipt=receipt)
        assert h.operation(operation_id)["status"] == "applying"
    finally:
        h.close()


def test_reconcile_rejects_typed_receipt_for_another_operation(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        with pytest.raises(KernelError):
            h.svc.delivery_reconcile(ctx("rc1"), operation_id,
                effect_receipt=EffectReceipt("foreign-operation", "applied"))
        assert h.operation(operation_id)["status"] == "applying"
    finally:
        h.close()


@pytest.mark.parametrize("fence_ref", [
    {"project_id": "other-project", "object_type": "fence", "object_id": "f1", "revision_id": "rev-1"},
    {"project_id": "proj-a", "object_type": "fence", "object_id": "missing", "revision_id": "rev-1"},
])
def test_reconcile_rejects_untrusted_fence_reference(tmp_path, fence_ref):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        with pytest.raises(KernelError):
            h.svc.delivery_reconcile(ctx("rc1"), operation_id,
                effect_receipt={"operation_id": operation_id, "status": "absent_final",
                    "fence_evidence_ref": fence_ref})
        assert h.operation(operation_id)["status"] == "applying"
    finally:
        h.close()


def test_provider_effect_receipt_identity_matches_reconciled_operation(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        receipt = h.svc.delivery_reconcile(ctx("rc1"), operation_id,
            effect_receipt=EffectReceipt(operation_id, "applied", verified_digest=_manifest(h, operation_id, digest).digest()))
        assert receipt.status == "committed"
        assert h.operation(operation_id)["status"] == "applied"
    finally:
        h.close()


def test_external_fence_flag_without_evidence_cannot_prove_absence(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("as1"), operation_id)
        result = h.svc.delivery_reconcile(ctx("rc1"), operation_id,
            effect_receipt=EffectReceipt(operation_id, "absent_final"), external_fence=True)
        assert result.status == "committed"
        operation = h.operation(operation_id)
        assert operation["status"] == "unknown"
        assert operation["effect_status"] == "unknown"
    finally:
        h.close()


def test_reconcile_of_a_terminal_operation_is_a_no_op(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation, _, _ = h.applied()
        before = h.operation(operation.object_id)
        receipt = h.svc.delivery_reconcile(ctx("rc1"), operation.object_id)
        assert receipt.status == "committed"
        assert receipt.object_refs == ()
        assert h.operation(operation.object_id) == before
    finally:
        h.close()


def test_reconcile_requires_the_delivery_capability(tmp_path):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval_id, digest = h.approved()
        claim = h.svc.claim_delivery(ctx("cl1"), approval_id, digest)
        operation_id = claim.object_refs[0].object_id
        import pytest
        from project_kernel.contracts.errors import KernelError
        with pytest.raises(KernelError) as denied:
            h.svc.delivery_reconcile(
                ctx("rc-nocap", principal="tool-2", caps=frozenset({"project.read"})),
                operation_id)
        assert denied.value.error.code == "PERMISSION_DENIED"
        assert h.operation(operation_id)["status"] == "claimed"
    finally:
        h.close()


@pytest.mark.parametrize("wrong_digest", [None, "a" * 64])
def test_provider_receipt_with_unverified_digest_stays_unknown(tmp_path, wrong_digest):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval, digest = h.approved()
        claimed = h.svc.claim_delivery(ctx("claim"), approval, digest)
        oid = claimed.object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("start"), oid)
        h.provider.effect_query = lambda operation_id: EffectReceipt(
            operation_id, "applied", verified_digest=wrong_digest)
        h.svc.delivery_reconcile(ctx("reconcile"), oid)
        assert h.operation(oid)["status"] == "unknown"
    finally:
        h.close()


def test_existing_fence_cannot_release_another_operation(tmp_path):
    from p04_delivery.helpers import seed_revision
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval, digest = h.approved()
        oid = h.svc.claim_delivery(ctx("claim"), approval, digest).object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("start"), oid)
        fence = seed_revision(h.store, "fence", "foreign", {"operation_id": "other-op"}, "fence")
        with pytest.raises(KernelError):
            h.svc.delivery_reconcile(ctx("reconcile"), oid,
                effect_receipt=EffectReceipt(oid, "absent_final", fence_evidence_ref=fence))
        assert h.operation(oid)["status"] == "applying"
    finally:
        h.close()


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_reconcile_does_not_trust_manifest_when_artifact_is_damaged(tmp_path, damage):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval, digest = h.approved()
        oid = h.svc.claim_delivery(ctx("claim"), approval, digest).object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("start"), oid)
        manifest = _manifest(h, oid, digest)
        assert h.exporter.export(manifest, "exports").state == "succeeded"
        artifact = h.exporter._artifact_path(h.exporter._target(oid), manifest.artifacts[0])
        if damage == "missing":
            artifact.unlink()
        else:
            artifact.write_bytes(b"changed after export")
        h.svc.delivery_reconcile(ctx("reconcile"), oid)
        assert h.operation(oid)["status"] == "unknown"
        assert not artifact.exists() if damage == "missing" else artifact.read_bytes() == b"changed after export"
    finally:
        h.close()


@pytest.mark.parametrize("terminal", ["false", "true", 1, [], {}])
def test_provider_truthy_terminal_does_not_prove_final_absence(tmp_path, terminal):
    h = Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval, digest = h.approved()
        oid = h.svc.claim_delivery(ctx("claim"), approval, digest).object_refs[0].object_id
        h.svc.apply_start_delivery(ctx("start"), oid)
        h.provider.effect_query = lambda operation: {"operation_id": operation,
            "status": "absent_final", "execution_terminal": terminal}
        h.svc.delivery_reconcile(ctx("reconcile"), oid)
        assert h.operation(oid)["status"] == "unknown"
    finally:
        h.close()
