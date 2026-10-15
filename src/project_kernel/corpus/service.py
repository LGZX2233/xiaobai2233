"""P09 corpus service: candidate build, human review, authorized export, cleanup plan.

The service owns the *separation* the design demands:

* `dataset.build` only produces a candidate manifest (filter/clean/review-candidate);
* `dataset.review` records the human per-sample quality verdicts and publishes the
  reviewed dataset revision;
* `dataset.export` needs that reviewed revision *and* an independent human decision
  whose action/target/digest match, then publishes one immutable dataset version;
* `artifacts.plan_cleanup` only produces a retention plan, never a deletion.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..contracts import ObjectRef, sha256_digest
from ..contracts.dto import CommandContext, CommandReceipt, ResolvedScope
from ..contracts.errors import (
    KernelError,
    artifact_digest_mismatch,
    capability_unavailable,
    human_identity_unavailable,
    invalid_input,
    permission_denied,
    reference_not_found,
    scope_mismatch,
)
from ..data.queries.service import QueryService
from ..data.store.store import Store
from ..application.security import require_scope
from ..data.store.uow import UnitOfWork
from . import exporter
from .models import (
    REVIEW_STATUS_REVIEWED,
    CleanupEntry,
    CleanupPlan,
    DatasetManifest,
    DatasetPolicy,
    ExportReceipt,
    Sample,
    SampleReview,
    ScriptArtifact,
    ScriptTestResult,
    SplitSpec,
    Tombstone,
)

SAMPLE_TYPE = "sample"
DATASET_MANIFEST_TYPE = "dataset_manifest"
DATASET_REVIEW_TYPE = "dataset_review"
DATASET_EXPORT_TYPE = "dataset_export"
SCRIPT_TYPE = "script"
CLEANUP_PLAN_TYPE = "cleanup_plan"

CANDIDATE_POINTER = "candidate"
REVIEWED_POINTER = "reviewed"
EXPORTED_POINTER = "exported"
CURRENT_POINTER = "current"

EXPORT_CAPABILITY = "dataset.export"
ADMIN_CAPABILITY = "project.admin"
READ_CAPABILITY = "project.read"

#: Revision types whose committed payloads count as script references.
REFERENCE_TYPES: tuple[str, ...] = (
    "dataset_manifest", "dataset_review", "dataset_export", "delivery_operation",
    "delivery_snapshot", "approval", "knowledge", "artifact", "archive_manifest",
)

#: Retention classes that always keep the artifact.
HOLD_CLASSES: frozenset[str] = frozenset({"permanent", "legal_hold"})

_SINK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class CorpusService:
    """Corpus/dataset capability for one project store."""

    def __init__(self, store: Store, *, policies: Mapping[str, DatasetPolicy] | None = None,
                 purposes: Mapping[str, str] | None = None,
                 sink_root: Path | str | None = None,
                 queries: QueryService | None = None):
        self.store = store
        self.policies = dict(policies or {})
        self.purposes = dict(purposes or {})
        self.sink_root = Path(sink_root) if sink_root is not None else None
        self.queries = queries or QueryService(store)

    # -- permissions ---------------------------------------------------------
    def _require(self, scope: ResolvedScope, capability: str) -> None:
        require_scope(self.store, scope, capability)

    def _resolve_policy(self, policy_ref: ObjectRef) -> DatasetPolicy:
        policy = self.policies.get(policy_ref.revision_id) or self.policies.get(policy_ref.object_id)
        if policy is not None:
            return policy
        row = self.store.get_revision(policy_ref)
        if row is None:
            raise KernelError(reference_not_found(
                f"dataset policy revision {policy_ref.revision_id} not found"))
        return DatasetPolicy.from_payload(row["payload"])

    def _resolve_manifest_policy(self, manifest: DatasetManifest) -> DatasetPolicy:
        if not manifest.policy_ref:
            raise KernelError(invalid_input("manifest carries no policy_ref"))
        return self._resolve_policy(ObjectRef.from_dict(manifest.policy_ref))

    def _resolve_purpose(self, purpose_ref: ObjectRef) -> str:
        """The purpose is fixed by the policy: an exported dataset cannot be re-purposed."""
        purpose = (self.purposes.get(purpose_ref.revision_id)
                   or self.purposes.get(purpose_ref.object_id))
        if purpose is not None:
            return purpose
        row = self.store.get_revision(purpose_ref)
        if row is None:
            raise KernelError(reference_not_found(
                f"dataset purpose revision {purpose_ref.revision_id} not found"))
        value = row["payload"].get("purpose")
        if not value:
            raise KernelError(invalid_input("purpose revision carries no purpose"))
        return str(value)

    def _check_as_of(self, as_of: str) -> int:
        if not str(as_of).isdigit():
            raise KernelError(invalid_input("as_of must be a non-negative integer watermark"))
        watermark = self.store.next_commit_seq() - 1
        if int(as_of) > watermark:
            raise KernelError(invalid_input(
                f"as_of {as_of} is beyond the committed watermark {watermark}"))
        return int(as_of)

    # -- ledger reads --------------------------------------------------------
    def _read_revision(self, ref: ObjectRef) -> dict[str, Any]:
        if ref.project_id != self.store.project_id:
            raise KernelError(scope_mismatch("revision belongs to another project"))
        row = self.store.get_revision(ref)
        if row is None:
            raise KernelError(reference_not_found(
                f"{ref.object_type}/{ref.object_id}@{ref.revision_id} not found"))
        return row

    def _latest_revisions(self, object_type: str, as_of_seq: int
                          ) -> list[tuple[str, str, int, dict[str, Any]]]:
        """Latest revision per object id at or before as_of_seq.

        Reads through the P06 typed read API (`QueryService.latest_revisions`,
        project-scoped and as_of-bounded) instead of touching the connection.
        Returns (object_id, revision_id, commit_seq, payload).
        """
        rows = self.queries.latest_revisions(object_type, as_of_seq=str(as_of_seq))
        return [(str(row["object_id"]), str(row["revision_id"]), int(row["commit_seq"]),
                 dict(row["payload"])) for row in rows]

    def _collect_samples(self, as_of_seq: int) -> list[Sample]:
        return [Sample.from_payload(payload)
                for _, _, _, payload in self._latest_revisions(SAMPLE_TYPE, as_of_seq)]

    # -- dataset.build -------------------------------------------------------
    def build(self, ctx: CommandContext, payload: Mapping[str, Any]) -> CommandReceipt:
        self._require(ctx.scope, EXPORT_CAPABILITY)
        policy_ref = ObjectRef.from_dict(payload["policy_ref"])
        purpose_ref = ObjectRef.from_dict(payload["purpose_ref"])
        spec = SplitSpec.from_payload(payload["split_spec"])
        source_as_of = str(payload["source_as_of"])
        as_of_seq = self._check_as_of(source_as_of)
        policy = self._resolve_policy(policy_ref)
        purpose = self._resolve_purpose(purpose_ref)
        if purpose != policy.purpose:
            raise KernelError(invalid_input(
                f"purpose_ref purpose {purpose!r} does not match policy purpose "
                f"{policy.purpose!r}"))
        manifest = exporter.build_manifest(
            policy, self._collect_samples(as_of_seq), project_id=self.store.project_id,
            spec=spec, source_as_of=source_as_of, purpose_ref=purpose_ref.to_dict(),
            policy_ref=policy_ref.to_dict())

        def cb(h: Any) -> None:
            ref = h.records.append_revision(
                DATASET_MANIFEST_TYPE, policy.dataset_id, manifest.to_dict(),
                "p09.dataset_manifest.v1")
            h.records.publish_head(ref, CANDIDATE_POINTER)
            h.outcome.object_refs = (ref,)
            h.outcome.operation_id = policy.dataset_id
            h.audit("dataset.built", {"manifest_digest": manifest.digest(),
                                      "sample_count": len(manifest.samples),
                                      "exclusion_stats": dict(manifest.exclusion_stats)},
                    object_refs=[ref.to_dict()])
        return UnitOfWork(self.store, ctx, "dataset.build").execute(cb)

    # -- dataset.review (human only) -----------------------------------------
    def review(self, ctx: CommandContext, payload: Mapping[str, Any],
               *, is_human: bool) -> CommandReceipt:
        self._require(ctx.scope, EXPORT_CAPABILITY)
        if not is_human:
            raise KernelError(human_identity_unavailable())
        dataset_ref = ObjectRef.from_dict(payload["dataset_ref"])
        if dataset_ref.object_type != DATASET_MANIFEST_TYPE:
            raise KernelError(invalid_input("dataset.review requires a candidate manifest revision"))
        candidate = DatasetManifest.from_dict(self._read_revision(dataset_ref)["payload"])
        reviews = [SampleReview.from_payload(item, reviewer_id=ctx.scope.principal_id, is_human=True)
                   for item in payload["sample_reviews"]]
        known = {str(row["sample_id"]) for row in candidate.samples}
        unknown = sorted({review.sample_id for review in reviews if review.sample_id not in known})
        if unknown:
            raise KernelError(invalid_input(
                f"review references samples outside the candidate set: {unknown}"))
        policy = self._resolve_manifest_policy(candidate)
        reviewed = exporter.build_manifest(
            policy, candidate.candidate_samples(), project_id=self.store.project_id,
            spec=exporter.manifest_spec(candidate), source_as_of=str(candidate.source_as_of),
            purpose_ref=candidate.purpose_ref, policy_ref=candidate.policy_ref, reviews=reviews,
            review_status=REVIEW_STATUS_REVIEWED)
        body = {
            "dataset_id": candidate.dataset_id,
            "candidate_ref": dataset_ref.to_dict(),
            "candidate_manifest_digest": candidate.digest(),
            "policy_ref": candidate.policy_ref,
            "reviewer_id": ctx.scope.principal_id,
            "is_human": True,
            "reason": str(payload["reason"]),
            "sample_reviews": [review.to_dict() for review in reviews],
            "manifest": reviewed.to_dict(),
            "manifest_digest": reviewed.digest(),
        }

        def cb(h: Any) -> None:
            ref = h.records.append_revision(DATASET_REVIEW_TYPE, candidate.dataset_id, body,
                                            "p09.dataset_review.v1")
            h.records.publish_head(ref, REVIEWED_POINTER)
            h.outcome.object_refs = (ref,)
            h.outcome.operation_id = candidate.dataset_id
            h.audit("dataset.reviewed", {"manifest_digest": body["manifest_digest"],
                                         "reviewer_id": ctx.scope.principal_id,
                                         "reviewed_samples": len(reviews)},
                    object_refs=[ref.to_dict()])
        return UnitOfWork(self.store, ctx, "dataset.review").execute(cb)

    # -- dataset.export (verified human decision required) -------------------
    def export(self, ctx: CommandContext, payload: Mapping[str, Any]) -> CommandReceipt:
        """Claim the export durably before its one external write.

        The command receipt acknowledges the operation, not the file effect. A
        retry returns that receipt and only reconciles existing bytes; it cannot
        start another write after an uncertain outcome.
        """
        self._require(ctx.scope, EXPORT_CAPABILITY)
        uow = UnitOfWork(self.store, ctx, "dataset.export")
        if self.store.get_receipt(ctx.scope.principal_id, ctx.idempotency_key) is not None:
            receipt = uow.execute(lambda h: None)
            if receipt.status == "accepted" and receipt.operation_id:
                self.reconcile_export(ctx, receipt.operation_id)
            return receipt
        reviewed_ref = ObjectRef.from_dict(payload["reviewed_dataset_ref"])
        if reviewed_ref.object_type != DATASET_REVIEW_TYPE:
            raise KernelError(invalid_input("dataset.export requires a reviewed dataset revision"))
        sink_id = str(payload["sink_id"])
        sink = self._sink(sink_id)
        decision_ref = ObjectRef.from_dict(payload["human_decision_ref"])
        reviewed_row = self._read_revision(reviewed_ref)
        body = reviewed_row["payload"]
        manifest = DatasetManifest.from_dict(body["manifest"])
        manifest_digest = str(body["manifest_digest"])
        if manifest.digest() != manifest_digest:
            raise KernelError(artifact_digest_mismatch(
                "reviewed manifest body does not match its recorded digest"))
        target_ref = self._verify_human_decision(
            decision_ref, reviewed_ref, str(reviewed_row["digest"]), sink_id)
        if any(not row.get("review") or row["review"].get("verdict") != "accepted"
               for row in manifest.samples):
            raise KernelError(invalid_input("samples without an accepted human review cannot be exported"))
        if not manifest.completeness.get("complete"):
            raise KernelError(invalid_input("dataset is not complete"))
        version = f"r{reviewed_row['ordinal']}"
        operation_id = "dataset-export-" + sha256_digest({
            "project_id": self.store.project_id, "sink_id": sink_id,
            "dataset_id": manifest.dataset_id, "version": version})[:32]
        sink.directory(manifest, version=version)

        def claim(h: Any) -> None:
            self._verify_human_decision(decision_ref, reviewed_ref,
                                        str(reviewed_row["digest"]), sink_id)
            if self.store.get_head("dataset_export_operation", operation_id, CURRENT_POINTER):
                raise KernelError(invalid_input(
                    "dataset version already claimed; a published dataset is never overwritten"))
            operation = {"operation_id": operation_id, "status": "applying",
                         "effect_status": "unknown", "execution_terminal": False,
                         "reviewed_ref": reviewed_ref.to_dict(),
                         "human_decision_ref": decision_ref.to_dict(),
                         "target_ref": target_ref.to_dict(), "sink_id": sink_id,
                         "manifest": manifest.to_dict(), "manifest_digest": manifest_digest,
                         "version": version, "principal_id": ctx.scope.principal_id,
                         "input_hash": ctx.input_hash, "created_seq": h.records.commit_seq}
            ref = h.records.append_revision("dataset_export_operation", operation_id,
                                             operation, "p09.dataset_export_operation.v1")
            h.records.publish_head(ref, CURRENT_POINTER)
            h.outcome.object_refs = (ref,)
            h.outcome.operation_id = operation_id
            h.audit("dataset.export_claimed", {"operation_id": operation_id,
                                               "sink_id": sink_id}, object_refs=[ref.to_dict()])

        receipt = uow.execute(claim)
        if receipt.status != "accepted":
            return receipt
        if uow.did_commit:
            try:
                sink.write(manifest, version=version)
            except (OSError, ValueError):
                # Existing or partial output is uncertain; never overwrite it.
                pass
        self.reconcile_export(ctx, operation_id)
        return receipt

    def _operation(self, operation_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        head = self.store.get_head("dataset_export_operation", operation_id, CURRENT_POINTER)
        if head is None:
            raise KernelError(reference_not_found("dataset export operation not found"))
        ref = ObjectRef(self.store.project_id, "dataset_export_operation", operation_id,
                        head["revision_id"])
        return self._read_revision(ref)["payload"], head

    def reconcile_export(self, ctx: CommandContext, operation_id: str) -> dict[str, Any]:
        """Inspect a claimed destination; never execute another file write."""
        self._require(ctx.scope, EXPORT_CAPABILITY)
        operation, _ = self._operation(operation_id)
        if operation["status"] == "applied":
            return operation
        manifest = DatasetManifest.from_dict(operation["manifest"])
        effect, files = self._sink(operation["sink_id"]).inspect(
            manifest, version=operation["version"])
        state = "applied" if effect == "applied" else "unknown"
        if operation["status"] == state:
            return operation
        step = {"operation_id": operation_id, "state": state,
                "manifest_digest": manifest.digest()}
        settle_ctx = CommandContext(
            scope=ctx.scope, command_id=ctx.command_id,
            idempotency_key="dataset-settle-" + sha256_digest(step)[:40],
            input_hash=sha256_digest(step))

        def settle(h: Any) -> None:
            current, head = self._operation(operation_id)
            if current["status"] == "applied":
                return
            updated = {**current, "status": state, "effect_status": effect,
                       "execution_terminal": effect == "applied",
                       "settled_seq": h.records.commit_seq}
            refs = []
            if effect == "applied":
                exported = ExportReceipt(
                    dataset_id=manifest.dataset_id, version=operation["version"],
                    manifest_digest=manifest.digest(),
                    artifact_digest=exporter.artifact_digest(manifest),
                    sample_count=len(manifest.samples), sink_id=operation["sink_id"],
                    files=tuple(files), human_decision_ref=ObjectRef.from_dict(
                        operation["human_decision_ref"]))
                ref = h.records.append_revision(
                    DATASET_EXPORT_TYPE, manifest.dataset_id,
                    {"receipt": exported.to_dict(), "reviewed_ref": operation["reviewed_ref"],
                     "policy_ref": manifest.policy_ref, "operation_id": operation_id},
                    "p09.dataset_export.v1")
                exported_head = self.store.get_head(DATASET_EXPORT_TYPE, manifest.dataset_id,
                                                     EXPORTED_POINTER)
                h.records.publish_head(ref, EXPORTED_POINTER,
                                       expected_head_version=str(exported_head["head_version"])
                                       if exported_head else None)
                refs.append(ref)
                updated["export_ref"] = ref.to_dict()
            op_ref = h.records.append_revision("dataset_export_operation", operation_id,
                                                updated, "p09.dataset_export_operation.v1")
            h.records.publish_head(op_ref, CURRENT_POINTER,
                                   expected_head_version=str(head["head_version"]))
            h.outcome.object_refs = tuple([op_ref, *refs])
            h.audit("dataset.export_reconciled", step,
                    object_refs=[ref.to_dict() for ref in h.outcome.object_refs])
        result = UnitOfWork(self.store, settle_ctx, "dataset.export.reconcile").execute(settle)
        if result.status == "rejected":
            raise KernelError(result.error)
        return self._operation(operation_id)[0]

    def _verify_human_decision(self, decision_ref: ObjectRef, reviewed_ref: ObjectRef,
                               reviewed_digest: str, sink_id: str) -> ObjectRef:
        """Authorize exactly one reviewed revision and immutable sink description."""
        if decision_ref.object_type != "decision":
            raise KernelError(invalid_input("export requires a decision revision"))
        row = self._read_revision(decision_ref)
        payload = row["payload"]
        if payload.get("is_human") is not True:
            raise KernelError(human_identity_unavailable())
        if (row["payload_schema"] != "p04.decision.v1"
                or payload.get("subject_kind") != "dataset_export"
                or payload.get("action") != "dataset.export"
                or payload.get("decision") != "approved"
                or payload.get("target_scope") != "approved_export_sink"):
            raise KernelError(invalid_input("decision does not authorize dataset export"))
        head = self.store.get_head("decision", decision_ref.object_id, CURRENT_POINTER)
        if head is None or head["revision_id"] != decision_ref.revision_id:
            raise KernelError(invalid_input("decision is no longer current"))
        expires_at = payload.get("expires_at")
        if expires_at is not None:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
                raise KernelError(invalid_input("decision has expired"))
        if payload.get("subject_digest") != reviewed_digest:
            raise KernelError(artifact_digest_mismatch(
                "human decision does not bind this reviewed dataset revision"))
        if payload.get("subject_ref") != reviewed_ref.to_dict():
            raise KernelError(invalid_input("human decision targets another dataset revision"))
        target_ref = ObjectRef.from_dict(payload["target_ref"])
        target = self._read_revision(target_ref)["payload"]
        if (target.get("sink_id") != sink_id
                or target.get("target_scope") != "approved_export_sink"
                or (target.get("store_id") is not None
                    and target["store_id"] != self.store.store_id)):
            raise KernelError(permission_denied("human decision does not authorize this export sink"))
        return target_ref

    def _sink(self, sink_id: str) -> exporter.FileSystemSink:
        if not _SINK_ID.fullmatch(sink_id) or ":" in sink_id:
            raise KernelError(invalid_input(f"sink_id {sink_id!r} is not a valid sink id"))
        if self.sink_root is None:
            raise KernelError(capability_unavailable("no dataset sink is configured"))
        root = self.sink_root.resolve()
        destination = (root / sink_id).resolve()
        if destination.parent != root:
            raise KernelError(permission_denied("dataset sink leaves the configured output root"))
        return exporter.FileSystemSink(destination)

    # -- dataset.preview -----------------------------------------------------
    def preview(self, scope: ResolvedScope, payload: Mapping[str, Any], *,
                as_of_seq: str | None = None) -> dict[str, Any]:
        self._require(scope, READ_CAPABILITY)
        policy_ref = ObjectRef.from_dict(payload["policy_ref"])
        purpose_ref = ObjectRef.from_dict(payload["purpose_ref"])
        purpose = self._resolve_purpose(purpose_ref)
        as_of_seq = (self.store.next_commit_seq() - 1 if as_of_seq is None
                     else self._check_as_of(as_of_seq))
        best: tuple[tuple[int, int], ObjectRef, DatasetManifest] | None = None
        for object_type in (DATASET_MANIFEST_TYPE, DATASET_REVIEW_TYPE):
            for object_id, revision_id, commit_seq, body in self._latest_revisions(
                    object_type, as_of_seq):
                data = body["manifest"] if object_type == DATASET_REVIEW_TYPE else body
                manifest = DatasetManifest.from_dict(data)
                if manifest.policy_ref != policy_ref.to_dict():
                    continue
                if manifest.purpose_ref != purpose_ref.to_dict():
                    continue
                if manifest.purpose != purpose:
                    continue
                rank = (1 if object_type == DATASET_REVIEW_TYPE else 0, commit_seq)
                if best is None or rank > best[0]:
                    best = (rank,
                            ObjectRef(self.store.project_id, object_type, object_id, revision_id),
                            manifest)
        if best is None:
            return {"status": "no_candidate_manifest", "dataset_ref": None, "purpose": None,
                    "candidates": [], "exclusions": [], "exclusion_stats": {},
                    "counts": {}, "completeness": {"samples_included": 0, "complete": False}}
        _, ref, manifest = best
        return {
            "status": manifest.review_status,
            "dataset_ref": ref.to_dict(),
            "purpose": manifest.purpose,
            "purpose_ref": manifest.purpose_ref,
            "policy_ref": manifest.policy_ref,
            "source_as_of": manifest.source_as_of,
            "split_spec": dict(manifest.split_spec),
            "candidates": [
                {"sample_id": str(row["sample_id"]), "kind": str(row["kind"]),
                 "split": str(row["split"]), "sample_digest": str(row["sample_digest"]),
                 "failure_type": row.get("failure_type"), "sensitivity": row.get("sensitivity"),
                 "review_verdict": (row.get("review") or {}).get("verdict")}
                for row in manifest.samples],
            "exclusions": [dict(row) for row in manifest.exclusions],
            "exclusion_stats": dict(manifest.exclusion_stats),
            "counts": dict(manifest.counts),
            "completeness": dict(manifest.completeness),
        }

    # -- internal writers (trusted composition, no public command) -----------
    def record_sample(self, ctx: CommandContext, sample: Sample) -> ObjectRef:
        """Register one traceable candidate sample (internal port writer)."""
        self._require(ctx.scope, ADMIN_CAPABILITY)
        result: dict[str, Any] = {}

        def cb(h: Any) -> None:
            ref = h.records.append_revision(SAMPLE_TYPE, sample.sample_id, sample.to_payload(),
                                            "p09.sample.v1")
            h.records.publish_head(ref, CURRENT_POINTER)
            h.outcome.object_refs = (ref,)
            h.outcome.operation_id = sample.sample_id
            result["ref"] = ref
        UnitOfWork(self.store, ctx, "sample.register").execute(cb)
        return result["ref"]

    def record_script(self, ctx: CommandContext, script: ScriptArtifact) -> ObjectRef:
        """Register a script artifact; promotion is only ever *proposed*."""
        self._require(ctx.scope, ADMIN_CAPABILITY)
        result: dict[str, Any] = {}

        def cb(h: Any) -> None:
            ref = h.records.append_revision(SCRIPT_TYPE, script.script_id, script.to_payload(),
                                            "p09.script.v1")
            h.records.publish_head(ref, CURRENT_POINTER)
            h.outcome.object_refs = (ref,)
            h.outcome.operation_id = script.script_id
            h.audit("script.registered", {"promotion_status": script.promotion_status()},
                    object_refs=[ref.to_dict()])
            result["ref"] = ref
        UnitOfWork(self.store, ctx, "script.register").execute(cb)
        return result["ref"]

    # -- artifacts.plan_cleanup ---------------------------------------------
    def plan_cleanup(self, ctx: CommandContext, payload: Mapping[str, Any]) -> CommandReceipt:
        self._require(ctx.scope, ADMIN_CAPABILITY)
        retention_policy_ref = ObjectRef.from_dict(payload["retention_policy_ref"])
        as_of_seq = self._check_as_of(str(payload["as_of_seq"]))
        references = self._reference_blobs(as_of_seq)
        entries: list[CleanupEntry] = []
        for object_id, _, _, body in self._latest_revisions(SCRIPT_TYPE, as_of_seq):
            script = self._script_from_payload(object_id, body)
            referenced_by = tuple(sorted(
                f"{object_type}:{name}" for object_type, name, text in references
                if script.script_id in text or script.source_digest in text
                or any(result.evidence_digest and result.evidence_digest in text
                       for result in script.test_results)))
            reasons: list[str] = []
            if script.retention_class in HOLD_CLASSES:
                reasons.append(f"retention_class={script.retention_class}")
            if referenced_by:
                reasons.append("referenced by delivery/failure/knowledge/dataset/archive facts")
            if script.promotion_eligible:
                reasons.append("promotion candidate with passing test evidence")
            if reasons:
                entries.append(CleanupEntry(script.script_id, "keep", tuple(reasons), referenced_by))
            else:
                entries.append(CleanupEntry(
                    script.script_id, "eligible_for_removal",
                    (f"retention_class={script.retention_class}",
                     "no delivery/failure-reproduction/knowledge/dataset reference",
                     "deletion needs a separate explicit user action"), ()))
        plan = CleanupPlan(retention_policy_ref=retention_policy_ref.object_id,
                           as_of_seq=str(as_of_seq), entries=tuple(entries))

        def cb(h: Any) -> None:
            ref = h.records.append_revision(CLEANUP_PLAN_TYPE, retention_policy_ref.object_id,
                                            plan.to_dict(), "p09.cleanup_plan.v1")
            h.records.publish_head(ref, CURRENT_POINTER)
            h.outcome.object_refs = (ref,)
            h.outcome.operation_id = retention_policy_ref.object_id
            h.audit("artifacts.cleanup_planned",
                    {"entries": len(plan.entries), "deletions_performed": plan.deletions_performed},
                    object_refs=[ref.to_dict()])
        return UnitOfWork(self.store, ctx, "artifacts.plan_cleanup").execute(cb)

    def _script_from_payload(self, object_id: str, body: Mapping[str, Any]) -> ScriptArtifact:
        return ScriptArtifact(
            script_id=str(body.get("script_id", object_id)), purpose=str(body.get("purpose", "")),
            source_attempt_ref=ObjectRef.from_dict(body["source_attempt_ref"]),
            source_digest=str(body.get("source_digest", "")),
            input_schema_ref=str(body.get("input_schema_ref", "")),
            output_schema_ref=str(body.get("output_schema_ref", "")),
            runtime_env=body.get("runtime_env") or {},
            permissions=tuple(body.get("permissions") or ()),
            test_results=tuple(ScriptTestResult(name=str(item["name"]), status=str(item["status"]),
                                                evidence_digest=str(item.get("evidence_digest", "")),
                                                detail=str(item.get("detail", "")))
                               for item in body.get("test_results") or ()),
            reuse_results=tuple(body.get("reuse_results") or ()),
            retention_class=str(body.get("retention_class", "standard")))

    def _reference_blobs(self, as_of_seq: int) -> list[tuple[str, str, str]]:
        """Committed reference-bearing payloads: (type, id, payload text)."""
        blobs: list[tuple[str, str, str]] = []
        for object_type in REFERENCE_TYPES:
            for object_id, _, _, body in self._latest_revisions(object_type, as_of_seq):
                blobs.append((object_type, object_id,
                              json.dumps(body, sort_keys=True, ensure_ascii=False)))
        return blobs


def tombstone_for(sample: Sample, reason: str) -> dict[str, Any]:
    """Deleting content keeps its hash; history is never rewritten."""
    return Tombstone(object_type=SAMPLE_TYPE, object_id=sample.sample_id,
                     digest=sha256_digest(sample.to_payload()), reason=reason).to_dict()


__all__ = ["CorpusService", "tombstone_for"]
