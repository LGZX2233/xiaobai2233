"""Injected delivery effects retain approvals, receipts and durable uncertainty."""
from __future__ import annotations

from pathlib import Path

import pytest

from project_kernel.application.delivery.service import DeliveryService
from project_kernel.contracts.dto import ObjectRef
from project_kernel.data.queries.service import QueryService
from project_kernel.data.store.store import Store

from p04_delivery.helpers import Harness, ctx, patch_object
from p04_delivery.memory_provider import MemoryDeliveryProvider


def _memory_harness(tmp_path):
    harness = Harness(tmp_path)
    try:
        harness.to_delivery_ready()
        provider = MemoryDeliveryProvider(harness.storage)
        patch_object(harness.store, "delivery_target", "dt1", provider.target(), "memory-target")
        head = harness.store.get_head("delivery_target", "dt1", "current")
        harness.target_ref = ObjectRef("proj-a", "delivery_target", "dt1", head["revision_id"])
        harness.provider = provider
        harness.svc = DeliveryService(harness.store, provider=provider,
                                      artifact_storage=harness.storage)
        return harness
    except BaseException:
        harness.close()
        raise


def test_non_file_provider_publishes_the_approved_manifest_and_artifact(tmp_path):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        receipt = harness.svc.apply_delivery(ctx("memory-apply"), approval, "snap-1", digest)
        assert receipt.status == "accepted", receipt.error
        operation = QueryService(harness.store).operation_status(receipt.operation_id)
        assert operation["status"] == operation["effect_status"] == "applied"
        assert operation["sink_receipt"]["sink_id"] == "memory"
        effect = harness.provider.published[receipt.operation_id]
        assert effect["manifest"]["snapshot_digest"] == digest
        assert effect["manifest"]["required_sinks"] == ["memory"]
        assert effect["artifacts"] == {harness.artifact.sha256: b"deliverable content"}
        assert not (tmp_path / "exports" / receipt.operation_id).exists()
        assert harness.svc.apply_delivery(ctx("memory-apply"), approval, "snap-1", digest) == receipt
        assert harness.provider.apply_calls == [(receipt.operation_id, "memory")]
    finally:
        harness.close()


def test_observation_failure_keeps_receipt_and_recovers_after_restart_without_apply(tmp_path):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        provider = harness.provider
        provider.observation_unavailable = True
        receipt = harness.svc.apply_delivery(ctx("observe-failure"), approval, "snap-1", digest)
        assert receipt.status == "accepted", receipt.error
        operation = QueryService(harness.store).operation_status(receipt.operation_id)
        assert operation["status"] == operation["effect_status"] == "unknown"
        assert operation["sink_receipt"]["state"] == "succeeded"
        assert operation["execution_terminal"] is False
        assert len(QueryService(harness.store).project_overview()["blockers"]) == 1
        assert harness.svc.apply_delivery(ctx("observe-failure"), approval, "snap-1", digest) == receipt
        assert len(provider.observe_calls) == 1

        path = Path(harness.store.conn.execute("PRAGMA database_list").fetchone()[2])
        harness.store.close()
        harness.store = Store.open_project(path, "proj-a", "store-a")
        harness.svc = DeliveryService(harness.store, provider=provider,
                                      artifact_storage=harness.storage)
        assert harness.svc.apply_delivery(ctx("observe-failure"), approval, "snap-1", digest) == receipt
        assert harness.svc.delivery_reconcile(ctx("still-unavailable"), receipt.operation_id).status == "committed"
        assert QueryService(harness.store).operation_status(receipt.operation_id)["status"] == "unknown"
        provider.observation_unavailable = False
        recovered = harness.svc.delivery_reconcile(ctx("observation-restored"), receipt.operation_id)
        assert recovered.status == "committed", recovered.error
        assert QueryService(harness.store).operation_status(receipt.operation_id)["status"] == "applied"
        assert QueryService(harness.store).project_overview()["blockers"] == []
        provider.observation_updates = {"status": "absent_final", "execution_terminal": True}
        before = QueryService(harness.store).operation_status(receipt.operation_id)
        observed = len(provider.observe_calls)
        assert harness.svc.delivery_reconcile(ctx("terminal-reconcile"), receipt.operation_id).status == "committed"
        assert QueryService(harness.store).operation_status(receipt.operation_id) == before
        assert len(provider.observe_calls) == observed
        assert provider.apply_calls == [(receipt.operation_id, "memory")]
    finally:
        harness.close()


@pytest.mark.parametrize("changed_policy", ["namespace", "sink_ids"])
def test_restart_reconcile_requires_the_original_provider_target(tmp_path, monkeypatch, changed_policy):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        provider = harness.provider
        provider.observation_unavailable = True
        receipt = harness.svc.apply_delivery(ctx("original-target"), approval, "snap-1", digest)
        assert receipt.status == "accepted", receipt.error
        original = QueryService(harness.store).operation_status(receipt.operation_id)
        assert original["status"] == "unknown"
        original_observations = len(provider.observe_calls)

        path = Path(harness.store.conn.execute("PRAGMA database_list").fetchone()[2])
        harness.store.close()
        harness.store = Store.open_project(path, "proj-a", "store-a")
        harness.svc = DeliveryService(harness.store, provider=provider,
                                      artifact_storage=harness.storage)
        provider.observation_unavailable = False
        with monkeypatch.context() as changed:
            if changed_policy == "namespace":
                changed.setattr(provider, "namespace", "another-target")
            else:
                changed.setattr(provider, "sink_ids", frozenset())
            reconciled = harness.svc.delivery_reconcile(ctx("changed-target"), receipt.operation_id)
            assert reconciled.status == "committed", reconciled.error
            operation = QueryService(harness.store).operation_status(receipt.operation_id)
            assert operation["status"] == operation["effect_status"] == "unknown"
            assert operation["sink_receipt"] == original["sink_receipt"]
            assert len(provider.observe_calls) == original_observations
            assert harness.svc.apply_delivery(ctx("original-target"), approval, "snap-1", digest) == receipt

        recovered = harness.svc.delivery_reconcile(ctx("original-target-restored"), receipt.operation_id)
        assert recovered.status == "committed", recovered.error
        assert QueryService(harness.store).operation_status(receipt.operation_id)["status"] == "applied"
        assert provider.apply_calls == [(receipt.operation_id, "memory")]
    finally:
        harness.close()


@pytest.mark.parametrize("updates", [
    {"operation_id": None},
    {"operation_id": "another-operation"},
    {"status": "unrecognised"},
])
def test_invalid_provider_observation_keeps_accepted_receipt_and_unknown_effect(tmp_path, updates):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        provider = harness.provider
        provider.observation_updates = updates
        applied = harness.svc.apply_delivery(ctx("invalid-observation"), approval, "snap-1", digest)
        assert applied.status == "accepted", applied.error
        assert harness.svc.delivery_reconcile(ctx("invalid-reconcile"), applied.operation_id).status == "committed"
        operation = QueryService(harness.store).operation_status(applied.operation_id)
        assert operation["status"] == operation["effect_status"] == "unknown"
        assert operation["sink_receipt"]["state"] == "succeeded"
        assert harness.svc.apply_delivery(ctx("invalid-observation"), approval, "snap-1", digest) == applied
        assert provider.apply_calls == [(applied.operation_id, "memory")]
    finally:
        harness.close()


@pytest.mark.parametrize("verified_digest", [None, "a" * 64])
def test_provider_observation_with_unverified_digest_cannot_settle(tmp_path, verified_digest):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        provider = harness.provider
        provider.observation_updates = {"verified_digest": verified_digest}
        applied = harness.svc.apply_delivery(ctx("unverified"), approval, "snap-1", digest)
        assert applied.status == "accepted", applied.error
        assert harness.svc.delivery_reconcile(ctx("unverified-reconcile"), applied.operation_id).status == "committed"
        operation = QueryService(harness.store).operation_status(applied.operation_id)
        assert operation["status"] == operation["effect_status"] == "unknown"
        assert provider.apply_calls == [(applied.operation_id, "memory")]
    finally:
        harness.close()


@pytest.mark.parametrize("terminal", [None, False, "true", 1])
def test_provider_absence_requires_boolean_terminal_evidence(tmp_path, terminal):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        provider = harness.provider
        provider.publish_effect = False
        provider.observation_updates = {"status": "absent_final", "execution_terminal": terminal}
        applied = harness.svc.apply_delivery(ctx("nonterminal-absence"), approval, "snap-1", digest)
        assert applied.status == "accepted", applied.error
        assert harness.svc.delivery_reconcile(ctx("nonterminal-reconcile"), applied.operation_id).status == "committed"
        operation = QueryService(harness.store).operation_status(applied.operation_id)
        assert operation["status"] == "unknown"
        assert operation["execution_terminal"] is False
        assert not provider.published
        provider.observation_updates = {"status": "absent_final", "execution_terminal": True}
        assert harness.svc.delivery_reconcile(ctx("terminal-absence"), applied.operation_id).status == "committed"
        assert QueryService(harness.store).operation_status(applied.operation_id)["status"] == "failed"
        assert provider.apply_calls == [(applied.operation_id, "memory")]
    finally:
        harness.close()


def test_approval_cannot_authorize_a_changed_provider_namespace(tmp_path):
    harness = _memory_harness(tmp_path)
    try:
        approval, digest = harness.approved()
        harness.provider.namespace = "unreviewed"
        refused = harness.svc.apply_delivery(ctx("redirect-namespace"), approval, "snap-1", digest)
        assert refused.status == "rejected"
        assert refused.error.code == "PERMISSION_DENIED"
        assert not harness.provider.apply_calls
        assert not QueryService(harness.store).latest_revisions("delivery")
    finally:
        harness.close()


def test_provider_target_policy_cannot_bypass_declared_sink_ids(tmp_path, monkeypatch):
    harness = _memory_harness(tmp_path)
    try:
        patch_object(harness.store, "delivery_target", "dt1", {"sink_id": "unconfigured"}, "unconfigured-sink")
        head = harness.store.get_head("delivery_target", "dt1", "current")
        harness.target_ref = ObjectRef("proj-a", "delivery_target", "dt1", head["revision_id"])
        monkeypatch.setattr(harness.provider, "target_matches", lambda *args, **kwargs: True)
        approval, digest = harness.approved()
        refused = harness.svc.apply_delivery(ctx("unconfigured-apply"), approval, "snap-1", digest)
        assert refused.status == "rejected"
        assert refused.error.code == "PERMISSION_DENIED"
        assert not harness.provider.apply_calls
        assert not QueryService(harness.store).latest_revisions("delivery")
    finally:
        harness.close()
