"""P09 service tests against a real temporary SQLite store.

Review (human quality) and export authorization are separate steps: the sample
writer cannot label its own samples as reviewed or authorized.
"""
from __future__ import annotations

import json

import pytest
from project_kernel.contracts import ObjectRef, sha256_digest
from project_kernel.contracts.dto import CommandContext, ResolvedScope
from project_kernel.contracts.errors import KernelError
from project_kernel.corpus import (
    ADMIN_CAPABILITY,
    DATASET_REVIEW_TYPE,
    EXPORT_CAPABILITY,
    READ_CAPABILITY,
    CorpusService,
    ScriptArtifact,
    ScriptTestResult,
)

from p01_store.helpers import make_store

from .helpers import PROJ, ctx, policy, sample, scope, spec


def _admin_ctx(key="admin-1"):
    return ctx({ADMIN_CAPABILITY, EXPORT_CAPABILITY, READ_CAPABILITY}, key)


def _write_decision(store, *, digest, reviewed_ref, action="dataset.export", is_human=True,
                    decision="approved", key="decision-1", target_ref=None, sink_id="sink-1",
                    target_scope="approved_export_sink"):
    """TEST-ONLY: persist exact typed decision/target revisions, including negative cases."""
    from project_kernel.data.store.uow import UnitOfWork

    result = {}
    def cb(h):
        target = h.records.append_revision(
            "delivery_target", "target-" + key,
            {"sink_id": sink_id, "target_scope": target_scope}, "p05.delivery_target.v1")
        h.records.publish_head(target, "current")
        head = store.get_head("decision", "dec-export-1", "current")
        ref = h.records.append_revision(
            "decision", "dec-export-1",
            {"subject_kind": "dataset_export", "action": action, "decision": decision,
             "is_human": is_human, "reason": "approved export",
             "subject_digest": digest, "subject_ref": reviewed_ref.to_dict(),
             "target_scope": target_scope, "target_ref": (target_ref or target).to_dict()},
            "p04.decision.v1")
        h.records.publish_head(ref, "current",
                               expected_head_version=str(head["head_version"]) if head else None)
        h.outcome.object_refs = (ref,)
        result["ref"] = ref
    UnitOfWork(store, ctx({ADMIN_CAPABILITY}, key), "decision.record").execute(cb)
    return result["ref"]


def _service(tmp_path, *, policies=None, sink_root=None, purposes=None):
    store = make_store(tmp_path, project_id=PROJ)
    service = CorpusService(store,
                            policies=policies or {"rev-1": policy()},
                            purposes=purposes or {"rev-1": "evaluation"},
                            sink_root=sink_root or (tmp_path / "sink"))
    return store, service


def _policy_ref():
    return ObjectRef(PROJ, "dataset_policy", "ds", "rev-1")


def _purpose_ref():
    return ObjectRef(PROJ, "dataset_purpose", "eval-1", "rev-1")


def _watermark(store):
    """as_of is always an explicit committed watermark, never a guessed future value."""
    return str(store.next_commit_seq() - 1)


def _build_payload(store):
    return {"policy_ref": _policy_ref().to_dict(), "source_as_of": _watermark(store),
            "purpose_ref": _purpose_ref().to_dict(), "split_spec": spec().to_dict()}


def _register_samples(store, service, samples):
    for index, item in enumerate(samples):
        service.record_sample(_admin_ctx(f"sample-{index}"), item)


def test_build_creates_a_candidate_manifest_revision(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1"), sample("s2", input="other")])
        receipt = service.build(_admin_ctx("build-1"), _build_payload(store))

        assert receipt.status == "accepted"
        head = store.get_head("dataset_manifest", "ds", "candidate")
        assert head is not None
        ref = ObjectRef(PROJ, "dataset_manifest", "ds", head["revision_id"])
        manifest = store.get_revision(ref)["payload"]
        assert manifest["review_status"] == "candidate"
        assert manifest["counts"]["samples"] == 2
        assert manifest["completeness"]["reviewed"] == 0
    finally:
        store.close()


def test_build_rejects_a_purpose_that_does_not_match_the_policy(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1")])
        payload = _build_payload(store)
        payload["purpose_ref"] = ObjectRef(PROJ, "dataset_purpose", "train-1", "rev-9").to_dict()
        with pytest.raises(KernelError) as unknown:
            service.build(_admin_ctx("build-1"), payload)
        assert unknown.value.error.code == "REFERENCE_NOT_FOUND"

        repurposed = CorpusService(store, policies={"rev-1": policy()},
                                   purposes={"rev-1": "training"})
        with pytest.raises(KernelError) as mismatch:
            repurposed.build(_admin_ctx("build-2"), _build_payload(store))
        assert mismatch.value.error.code == "INVALID_INPUT"
    finally:
        store.close()


def test_build_rejects_future_source_as_of(tmp_path):
    store, service = _service(tmp_path)
    try:
        payload = _build_payload(store)
        payload["source_as_of"] = str(int(payload["source_as_of"]) + 99)
        with pytest.raises(KernelError) as exc:
            service.build(_admin_ctx("build-1"), payload)
        assert exc.value.error.code == "INVALID_INPUT"
    finally:
        store.close()


def test_review_requires_a_human_and_an_existing_sample(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1")])
        service.build(_admin_ctx("build-1"), _build_payload(store))
        head = store.get_head("dataset_manifest", "ds", "candidate")
        dataset_ref = ObjectRef(PROJ, "dataset_manifest", "ds", head["revision_id"])

        with pytest.raises(KernelError) as machine:
            service.review(_admin_ctx("review-1"),
                           {"dataset_ref": dataset_ref.to_dict(),
                            "sample_reviews": [{"sample_id": "s1", "verdict": "accepted",
                                                "reason": "ok"}],
                            "reason": "review"}, is_human=False)
        assert machine.value.error.code == "HUMAN_IDENTITY_UNAVAILABLE"

        with pytest.raises(KernelError) as unknown:
            service.review(_admin_ctx("review-2"),
                           {"dataset_ref": dataset_ref.to_dict(),
                            "sample_reviews": [{"sample_id": "nope", "verdict": "accepted",
                                                "reason": "ok"}],
                            "reason": "review"}, is_human=True)
        assert unknown.value.error.code == "INVALID_INPUT"
    finally:
        store.close()


def test_export_needs_reviewed_revision_and_matching_human_decision(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1"), sample("s2", input="other")])
        service.build(_admin_ctx("build-1"), _build_payload(store))
        candidate = ObjectRef(PROJ, "dataset_manifest", "ds",
                              store.get_head("dataset_manifest", "ds", "candidate")["revision_id"])

        with pytest.raises(KernelError) as not_reviewed:
            service.export(_admin_ctx("export-1"),
                           {"reviewed_dataset_ref": candidate.to_dict(), "sink_id": "sink-1",
                            "human_decision_ref": candidate.to_dict()})
        assert not_reviewed.value.error.code == "INVALID_INPUT"

        service.review(_admin_ctx("review-1"),
                       {"dataset_ref": candidate.to_dict(),
                        "sample_reviews": [{"sample_id": "s1", "verdict": "accepted", "reason": "ok"},
                                           {"sample_id": "s2", "verdict": "accepted", "reason": "ok"}],
                        "reason": "reviewed"}, is_human=True)
        reviewed_ref = ObjectRef(PROJ, DATASET_REVIEW_TYPE, "ds",
                                 store.get_head(DATASET_REVIEW_TYPE, "ds", "reviewed")["revision_id"])
        digest = store.get_revision(reviewed_ref)["digest"]

        wrong = _write_decision(store, digest="0" * 64, reviewed_ref=reviewed_ref, key="decision-2")
        with pytest.raises(KernelError) as mismatch:
            service.export(_admin_ctx("export-2"),
                           {"reviewed_dataset_ref": reviewed_ref.to_dict(), "sink_id": "sink-1",
                            "human_decision_ref": wrong.to_dict()})
        assert mismatch.value.error.code == "ARTIFACT_DIGEST_MISMATCH"

        machine_decision = _write_decision(store, digest=digest, reviewed_ref=reviewed_ref,
                                           is_human=False, key="decision-3")
        with pytest.raises(KernelError) as not_human:
            service.export(_admin_ctx("export-3"),
                           {"reviewed_dataset_ref": reviewed_ref.to_dict(), "sink_id": "sink-1",
                            "human_decision_ref": machine_decision.to_dict()})
        assert not_human.value.error.code == "HUMAN_IDENTITY_UNAVAILABLE"

        decision = _write_decision(store, digest=digest, reviewed_ref=reviewed_ref)
        # a machine caller may execute the export: the verification human became
        # the *decision revision*, not the caller's own claim
        receipt = service.export(_admin_ctx("export-4"),
                                 {"reviewed_dataset_ref": reviewed_ref.to_dict(),
                                  "sink_id": "sink-1", "human_decision_ref": decision.to_dict()})
        assert receipt.status == "accepted"

        exported = store.get_head("dataset_export", "ds", "exported")
        assert exported is not None
        export_body = store.get_revision(
            ObjectRef(PROJ, "dataset_export", "ds", exported["revision_id"]))["payload"]
        files = export_body["receipt"]["files"]
        assert len(files) == 2
        rows = [json.loads(line) for line in
                (tmp_path / "sink" / "sink-1" / "ds" / export_body["receipt"]["version"]
                 / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2
        assert all(row["review"]["verdict"] == "accepted" for row in rows)
    finally:
        store.close()


def test_unreviewed_sample_blocks_export(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1"), sample("s2", input="other")])
        service.build(_admin_ctx("build-1"), _build_payload(store))
        candidate = ObjectRef(PROJ, "dataset_manifest", "ds",
                              store.get_head("dataset_manifest", "ds", "candidate")["revision_id"])
        service.review(_admin_ctx("review-1"),
                       {"dataset_ref": candidate.to_dict(),
                        "sample_reviews": [{"sample_id": "s1", "verdict": "accepted", "reason": "ok"}],
                        "reason": "partial"}, is_human=True)
        reviewed_ref = ObjectRef(PROJ, DATASET_REVIEW_TYPE, "ds",
                                 store.get_head(DATASET_REVIEW_TYPE, "ds", "reviewed")["revision_id"])
        digest = store.get_revision(reviewed_ref)["digest"]
        decision = _write_decision(store, digest=digest, reviewed_ref=reviewed_ref)

        with pytest.raises(KernelError) as incomplete:
            service.export(_admin_ctx("export-1"),
                           {"reviewed_dataset_ref": reviewed_ref.to_dict(), "sink_id": "sink-1",
                            "human_decision_ref": decision.to_dict()})
        assert incomplete.value.error.code == "INVALID_INPUT"
    finally:
        store.close()


def test_republishing_the_same_version_is_refused(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1")])
        service.build(_admin_ctx("build-1"), _build_payload(store))
        candidate = ObjectRef(PROJ, "dataset_manifest", "ds",
                              store.get_head("dataset_manifest", "ds", "candidate")["revision_id"])
        service.review(_admin_ctx("review-1"),
                       {"dataset_ref": candidate.to_dict(),
                        "sample_reviews": [{"sample_id": "s1", "verdict": "accepted", "reason": "ok"}],
                        "reason": "reviewed"}, is_human=True)
        reviewed_ref = ObjectRef(PROJ, DATASET_REVIEW_TYPE, "ds",
                                 store.get_head(DATASET_REVIEW_TYPE, "ds", "reviewed")["revision_id"])
        digest = store.get_revision(reviewed_ref)["digest"]
        decision = _write_decision(store, digest=digest, reviewed_ref=reviewed_ref)
        payload = {"reviewed_dataset_ref": reviewed_ref.to_dict(), "sink_id": "sink-1",
                   "human_decision_ref": decision.to_dict()}
        assert service.export(_admin_ctx("export-1"), payload).status == "accepted"

        again = service.export(_admin_ctx("export-2"), payload)
        assert again.status == "rejected"
        assert again.error.code == "INVALID_INPUT"
        assert "never overwritten" in again.error.message
    finally:
        store.close()


def test_preview_reports_candidates_exclusions_purpose_and_completeness(tmp_path):
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1"), sample("s-todo", input="", output="")])
        query = {"policy_ref": _policy_ref().to_dict(), "purpose_ref": _purpose_ref().to_dict()}

        empty = service.preview(scope({READ_CAPABILITY}, principal="user-1"), query)
        assert empty["status"] == "no_candidate_manifest"
        assert empty["completeness"]["complete"] is False

        service.build(_admin_ctx("build-1"), _build_payload(store))
        preview = service.preview(scope({READ_CAPABILITY}, principal="user-1"), query)
        assert preview["status"] == "candidate"
        assert preview["purpose"] == "evaluation"
        assert [item["sample_id"] for item in preview["candidates"]] == ["s1"]
        assert preview["exclusions"][0]["reason"] == "EMPTY_TEMPLATE"
        assert preview["completeness"]["complete"] is False
    finally:
        store.close()


def test_cleanup_plan_keeps_referenced_scripts_and_never_deletes(tmp_path):
    store, service = _service(tmp_path)
    try:
        attempt_ref = ObjectRef(PROJ, "attempt", "attempt-1", "rev-1")
        referenced = ScriptArtifact(script_id="script-used", purpose="replay",
                                    source_attempt_ref=attempt_ref, source_digest="b" * 64,
                                    input_schema_ref="schema-in", output_schema_ref="schema-out",
                                    runtime_env={"python": "3.12"}, permissions=("exec",),
                                    test_results=(ScriptTestResult("t1", "passed", "c" * 64),))
        orphan = ScriptArtifact(script_id="script-orphan", purpose="scratch",
                                source_attempt_ref=attempt_ref, source_digest="d" * 64,
                                input_schema_ref="schema-in", output_schema_ref="schema-out",
                                runtime_env={"python": "3.12"}, permissions=("exec",),
                                test_results=(ScriptTestResult("t1", "failed", ""),))
        service.record_script(_admin_ctx("script-1"), referenced)
        service.record_script(_admin_ctx("script-2"), orphan)
        # the candidate manifest references the artifact digest of script-used
        service.record_sample(_admin_ctx("sample-1"),
                              sample("s1", source_digests=("b" * 64,)))
        service.build(_admin_ctx("build-1"), _build_payload(store))

        receipt = service.plan_cleanup(_admin_ctx("cleanup-1"),
                                       {"retention_policy_ref": _policy_ref().to_dict(),
                                        "as_of_seq": _watermark(store)})
        assert receipt.status == "accepted"
        head = store.get_head("cleanup_plan", "ds", "current")
        plan = store.get_revision(ObjectRef(PROJ, "cleanup_plan", "ds", head["revision_id"]))["payload"]
        entries = {entry["script_id"]: entry for entry in plan["entries"]}
        assert entries["script-used"]["decision"] == "keep"
        assert entries["script-used"]["referenced_by"] == ["dataset_manifest:ds"]
        assert entries["script-orphan"]["decision"] == "eligible_for_removal"
        assert plan["deletions_performed"] == 0
        assert plan["deletion_mode"] == "plan_only"
    finally:
        store.close()


def test_service_rejects_another_projects_scope(tmp_path):
    store, service = _service(tmp_path)
    try:
        foreign_scope = ResolvedScope(project_id="proj-b", store_id="store-a",
                                      principal_id="user-1",
                                      capabilities=frozenset({ADMIN_CAPABILITY}), mode="test")
        foreign = CommandContext(scope=foreign_scope, command_id="cmd-foreign",
                                 idempotency_key="foreign-1",
                                 input_hash=sha256_digest({"key": "foreign-1"}))
        with pytest.raises(KernelError) as exc:
            service.build(foreign, _build_payload(store))
        assert exc.value.error.code == "SCOPE_MISMATCH"
    finally:
        store.close()


def test_manifest_keeps_the_exact_source_revision_of_every_sample(tmp_path):
    """AC35: every sample can be traced back to an exact source revision."""
    store, service = _service(tmp_path)
    try:
        _register_samples(store, service, [sample("s1")])
        service.build(_admin_ctx("build-1"), _build_payload(store))
        head = store.get_head("dataset_manifest", "ds", "candidate")
        manifest = store.get_revision(
            ObjectRef(PROJ, "dataset_manifest", "ds", head["revision_id"]))["payload"]
        assert manifest["samples"][0]["source_refs"] == [
            {"project_id": PROJ, "object_type": "attempt", "object_id": "attempt-t1",
             "revision_id": "rev-1"}]
        assert manifest["samples"][0]["sample_digest"]
    finally:
        store.close()


def _ready_export(tmp_path):
    store, service = _service(tmp_path)
    _register_samples(store, service, [sample("s1")])
    built = service.build(_admin_ctx("build-1"), _build_payload(store))
    reviewed = service.review(_admin_ctx("review-1"), {
        "dataset_ref": built.object_refs[0].to_dict(),
        "sample_reviews": [{"sample_id": "s1", "verdict": "accepted", "reason": "reviewed"}],
        "reason": "review"}, is_human=True)
    ref = reviewed.object_refs[0]
    decision = _write_decision(store, digest=store.get_revision(ref)["digest"], reviewed_ref=ref)
    payload = {"reviewed_dataset_ref": ref.to_dict(), "sink_id": "sink-1",
               "human_decision_ref": decision.to_dict()}
    return store, service, payload


def test_export_sink_must_match_the_approved_target(tmp_path):
    store, service, payload = _ready_export(tmp_path)
    try:
        with pytest.raises(KernelError) as wrong:
            service.export(_admin_ctx("export-wrong"), {**payload, "sink_id": "sink-2"})
        assert wrong.value.error.code == "PERMISSION_DENIED"
        assert not (tmp_path / "sink").exists()
    finally:
        store.close()


def test_durable_export_receipt_replays_before_effects_after_reconstruction(tmp_path):
    store, service, payload = _ready_export(tmp_path)
    try:
        first = service.export(_admin_ctx("export-1"), payload)
        rebuilt = CorpusService(store, sink_root=tmp_path / "sink")
        replay = rebuilt.export(_admin_ctx("export-1"), payload)
        assert replay.to_dict() == first.to_dict()
        assert rebuilt._operation(first.operation_id)[0]["status"] == "applied"
        assert len(list((tmp_path / "sink").rglob("samples.jsonl"))) == 1
    finally:
        store.close()


def test_conflicting_export_key_never_writes_another_sink(tmp_path):
    from dataclasses import replace
    store, service, payload = _ready_export(tmp_path)
    try:
        service.export(_admin_ctx("export-1"), payload)
        conflict = replace(_admin_ctx("export-1"), input_hash=sha256_digest({"different": True}))
        with pytest.raises(KernelError) as rejected:
            service.export(conflict, {**payload, "sink_id": "sink-2"})
        assert rejected.value.error.code == "IDEMPOTENCY_CONFLICT"
        assert not (tmp_path / "sink" / "sink-2").exists()
    finally:
        store.close()


def test_export_recovers_receipt_loss_by_reading_existing_bytes(tmp_path, monkeypatch):
    store, service, payload = _ready_export(tmp_path)
    try:
        def receipt_loss(*args):
            raise RuntimeError("simulated process stop after external write")
        monkeypatch.setattr(service, "reconcile_export", receipt_loss)
        with pytest.raises(RuntimeError):
            service.export(_admin_ctx("export-1"), payload)
        rebuilt = CorpusService(store, sink_root=tmp_path / "sink")
        receipt = rebuilt.export(_admin_ctx("export-1"), payload)
        assert rebuilt._operation(receipt.operation_id)[0]["status"] == "applied"
        assert store.get_head("dataset_export", "ds", "exported") is not None
    finally:
        store.close()


def test_partial_export_remains_unknown_and_retry_does_not_write(tmp_path, monkeypatch):
    from project_kernel.corpus.exporter import FileSystemSink
    store, service, payload = _ready_export(tmp_path)
    writes = []
    def partial(self, manifest, *, version):
        writes.append(version)
        directory = self.directory(manifest, version=version)
        directory.mkdir(parents=True)
        (directory / "samples.jsonl").write_bytes(b"partial")
        raise OSError("interrupted write")
    monkeypatch.setattr(FileSystemSink, "write", partial)
    try:
        first = service.export(_admin_ctx("export-1"), payload)
        replay = service.export(_admin_ctx("export-1"), payload)
        assert first.to_dict() == replay.to_dict()
        assert writes == ["r1"]
        assert service._operation(first.operation_id)[0]["status"] == "unknown"
        assert store.get_head("dataset_export", "ds", "exported") is None
    finally:
        store.close()


def test_export_decision_cannot_use_an_alias_action_or_nonapproved_scope(tmp_path):
    store, service, payload = _ready_export(tmp_path)
    try:
        ref = ObjectRef.from_dict(payload["reviewed_dataset_ref"])
        for index, override in enumerate(({"action": "export"}, {"target_scope": "shared"},
                                           {"decision": "rejected"})):
            decision = _write_decision(store, digest=store.get_revision(ref)["digest"],
                                       reviewed_ref=ref, key=f"bad-{index}", **override)
            with pytest.raises(KernelError) as rejected:
                service.export(_admin_ctx(f"export-{index}"),
                               {**payload, "human_decision_ref": decision.to_dict()})
            assert rejected.value.error.code == "INVALID_INPUT"
        assert not (tmp_path / "sink").exists()
    finally:
        store.close()
