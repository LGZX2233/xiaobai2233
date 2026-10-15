"""DeliveryService: verification -> approval -> real delivery -> closure (P04).

Contract spine (design 03/04): freeze an immutable snapshot (JCS+SHA-256 over
the body, shell metadata excluded), request a human approval, only a trusted
human may decide/revoke, apply through an injected delivery provider, and settle
with a queried effect. Reconciliation never replays an external write and a
missing target alone is never proof of "no effect".

Everything is persisted on the P01 revision ledger: reports, validity
assessments, decisions, operations, archive manifests and archive status are
append-only revisions, so an old report/receipt is never overwritten.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping

from ...contracts import (
    ApprovalStatus,
    ArchiveSinkState,
    DeliveryState,
    EffectStatus,
    ValidationError,
    sha256_digest,
    validate_delivery_snapshot_body,
)
from ...contracts.dto import (
    AcceptanceItem,
    ArtifactRef,
    CheckResult,
    CommandContext,
    CommandReceipt,
    EffectReceipt,
    ObjectRef,
)
from ...contracts.errors import (
    BlockError,
    KernelError,
    approval_invalid,
    artifact_digest_mismatch,
    capability_unavailable,
    evidence_stale,
    human_identity_unavailable,
    invalid_input,
    permission_denied,
    reference_not_found,
    required_fact_unknown,
    scope_mismatch,
    snapshot_changed,
    verification_failed,
)
from ...data.store.store import Store
from ..security import require_scope
from ...data.store.uow import UnitOfWork
from ...evidence.archive import ArchiveManifest
from ...internal.delivery_provider_ports import DeliveryProvider
from ...domain import delivery as delivery_rules
from ...domain import flow

CAP_VERIFICATION = "verification.review"
CAP_APPROVAL = "approval.decide"
CAP_DELIVERY = "delivery.apply"
CAP_DISPATCH = "dispatch.confirm"

#: action -> (required subject_kind, required capability) for `decision.record`
#: (design 04 §9). There is deliberately no catch-all "human may decide anything"
#: permission, and a delivery approval never substitutes for these decisions.
DECISION_ACTIONS: dict[str, tuple[str, str]] = {
    "restore.apply": ("restore_plan", "project.admin"),
    "knowledge.promote": ("knowledge_promotion", "knowledge.share"),
    "dataset.export": ("dataset_export", "dataset.export"),
}

_TERMINAL_DELIVERY = (DeliveryState.APPLIED.value, DeliveryState.FAILED.value)


def _new_id(kind: str) -> str:
    return f"{kind}-{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snapshot_changed(message: str) -> BlockError:
    """SNAPSHOT_CHANGED with a specific reason (the catalog helper has no message)."""
    return BlockError("SNAPSHOT_CHANGED", message, category="conflict",
                      recovery_action="re-request the approval for a new snapshot")


def _utc_in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)) \
        .replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _expired_at(value: str | None) -> bool:
    if not value:
        return False
    return _parse_ts(value) <= datetime.now(timezone.utc)


class DeliveryService:
    def __init__(self, store: Store, provider: DeliveryProvider | None = None,
                 artifact_storage: Any | None = None):
        self.store = store
        #: The provider owns all external delivery effects and observations.
        self.provider = provider
        #: Required artifacts can freeze only with a configured verification port.
        self.artifact_storage = artifact_storage

    # ------------------------------------------------------------------ reads
    def _head_payload(self, object_type: str, object_id: str
                      ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        head = self.store.get_head(object_type, object_id, "current")
        if head is None:
            return None, None
        rev = self.store.get_revision(
            ObjectRef(self.store.project_id, object_type, object_id, head["revision_id"]))
        return (rev["payload"] if rev else None), head

    def _head_status(self, object_type: str, object_id: str) -> str | None:
        payload, _ = self._head_payload(object_type, object_id)
        return payload.get("status") if payload else None

    def _snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        payload, _ = self._head_payload("delivery_snapshot", snapshot_id)
        return payload

    def _delivery_target(self, snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
        """Resolve the target revision pinned by the unchanged frozen body."""
        if sha256_digest(snapshot["body"]) != snapshot["digest"]:
            raise KernelError(_snapshot_changed("frozen snapshot body digest differs"))
        raw = snapshot["body"]["delivery"]["target_ref"]
        row = self._exact_revision(raw, kind="delivery_target")
        key = ":".join(raw[name] for name in
                       ("project_id", "object_type", "object_id", "revision_id"))
        expected = snapshot["reference_digests"].get(key)
        if expected != row["digest"] or sha256_digest(row["payload"]) != expected:
            raise KernelError(artifact_digest_mismatch("frozen delivery target digest differs"))
        target = row["payload"]
        if not isinstance(target.get("sink_id"), str) or not target["sink_id"]:
            raise KernelError(invalid_input("delivery target requires a sink_id"))
        return target

    def _require_delivery_provider(self, snapshot: Mapping[str, Any], *,
                                   scope_mode: str) -> Mapping[str, Any]:
        """Require the configured provider to accept the approved sink and target."""
        if self.provider is None:
            raise KernelError(capability_unavailable("no delivery provider registered"))
        target = self._delivery_target(snapshot)
        if (target["sink_id"] not in self.provider.sink_ids
                or not self.provider.target_matches(target, scope_mode=scope_mode)):
            raise KernelError(permission_denied(
                "approved target is outside the configured delivery provider"))
        return target

    def _delivery_manifest(self, operation_id: str,
                           snapshot: Mapping[str, Any]) -> ArchiveManifest:
        """Build the same manifest for application and subsequent effect reads."""
        target = self._delivery_target(snapshot)
        artifacts = tuple(ArtifactRef(a["artifact_id"], a["sha256"], a["size_bytes"],
                                      a["media_type"], a["required"])
                          for a in snapshot["body"].get("artifacts", []))
        return ArchiveManifest(
            manifest_id=operation_id, snapshot_digest=snapshot["digest"],
            delivery_operation_refs=(operation_id,), artifacts=artifacts,
            required_sinks=(target["sink_id"],))

    def _verification_state(self, ref: ObjectRef) -> dict[str, Any] | None:
        """Latest state of a verification object (head wins over the pinned rev)."""
        payload, _ = self._head_payload(ref.object_type, ref.object_id)
        if payload is not None:
            return payload
        rev = self.store.get_revision(ref)
        return rev["payload"] if rev else None

    def archive_status_for_task(self, task_id: str) -> dict[str, Any] | None:
        payload, _ = self._head_payload("archive_status", task_id)
        return payload

    def _approval_heads(self) -> list[str]:
        rows = self.store.conn.execute(
            "SELECT object_id FROM entity_head WHERE type='approval' AND pointer_name='current'"
        ).fetchall()
        return [r[0] for r in rows]

    def _delivery_heads(self) -> list[str]:
        rows = self.store.conn.execute(
            "SELECT object_id FROM entity_head WHERE type='delivery' AND pointer_name='current'"
        ).fetchall()
        return [r[0] for r in rows]

    def _attempt_heads(self) -> list[str]:
        rows = self.store.conn.execute(
            "SELECT object_id FROM entity_head WHERE type='attempt' AND pointer_name='current'"
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------- guards
    def _require(self, capability: str, ctx: CommandContext) -> None:
        require_scope(self.store, ctx.scope, capability)

    @staticmethod
    def _require_human(is_human: bool) -> None:
        if not is_human:
            raise KernelError(human_identity_unavailable())

    @staticmethod
    def _derive(ctx: CommandContext, suffix: str, payload: Any) -> CommandContext:
        """A distinct idempotency key for an internal sub-step.

        Reusing the caller's key for several UnitOfWork calls would make the
        second call return the first receipt instead of executing.
        """
        return CommandContext(scope=ctx.scope, command_id="cmd-" + uuid.uuid4().hex[:12],
                              idempotency_key=f"{ctx.idempotency_key}:{suffix}",
                              input_hash=sha256_digest({"step": suffix, "payload": payload}))

    # ------------------------------------------------- decisive eligibility
    @staticmethod
    def _required_artifact_refs(body: Mapping[str, Any]) -> tuple[ArtifactRef, ...]:
        return tuple(ArtifactRef(a["artifact_id"], a["sha256"], a["size_bytes"],
                                 a["media_type"], a["required"])
                     for a in body.get("artifacts", ()) if a.get("required"))

    def _basis(self, body: Mapping[str, Any]) -> dict[str, str]:
        """Content digest of every decisive input referenced by the snapshot.

        Unrelated display-name/audit edits keep the same digest, so they never
        invalidate an approval; a real content change does.
        """
        basis: dict[str, str] = {}
        for ref in delivery_rules.iter_refs(body):
            payload, _ = self._head_payload(ref["object_type"], ref["object_id"])
            projection = (delivery_rules.decisive_projection(ref["object_type"], payload)
                          if payload is not None else "<absent>")
            basis[delivery_rules.ref_key(ref)] = sha256_digest(projection)
        for raw in body.get("verification_refs", ()):
            report = self._verification_state(ObjectRef.from_dict(raw))
            candidate_ref = (report or {}).get("candidate_manifest_ref")
            if candidate_ref:
                candidate, _ = self._head_payload(candidate_ref["object_type"], candidate_ref["object_id"])
                basis[delivery_rules.ref_key(candidate_ref)] = sha256_digest(
                    delivery_rules.decisive_projection("candidate_manifest", candidate))
        return basis

    def _snapshot_eligible(self, snap: Mapping[str, Any]) -> bool:
        return self._basis(snap["body"]) == snap.get("eligibility_basis")

    def refresh_approvals(self, ctx: CommandContext) -> CommandReceipt | None:
        """Persist supersession after decisive publication, preserving started effects.

        @param ctx Trusted project command context authorizing the publication.
        @returns The assessment receipt, or None when no approval needs an update.
        """
        capability = next((name for name in ("design.write", CAP_APPROVAL, CAP_DELIVERY,
            CAP_VERIFICATION, CAP_DISPATCH) if ctx.scope.has(name)), CAP_DISPATCH)
        self._require(capability, ctx)
        moved = {}
        for approval_id in self._approval_heads():
            payload, head = self._head_payload("approval", approval_id)
            if (payload is None or head is None or payload.get("apply_started")
                    or payload.get("status") not in {"pending", "approved"}):
                continue
            snap = self._snapshot(payload["snapshot_id"])
            if snap is not None and not self._snapshot_eligible(snap):
                moved[approval_id] = {"revision_id": head["revision_id"], "basis": self._basis(snap["body"])}
        if not moved:
            return None
        assessment = self._derive(ctx, "approval-validity:" + sha256_digest(moved), moved)
        def cb(h):
            refs = []
            for approval_id in moved:
                payload, head = self._head_payload("approval", approval_id)
                if (payload is None or head is None or payload.get("apply_started")
                        or payload.get("status") not in {"pending", "approved"}):
                    continue
                snap = self._snapshot(payload["snapshot_id"])
                if snap is None or self._snapshot_eligible(snap):
                    continue
                ref = h.records.append_revision("approval", approval_id,
                    {**payload, "status": "superseded", "supersede_reason": "decisive input changed",
                     "superseded_at": _utc_now()}, "approval.v1")
                h.records.publish_head(ref, "current", expected_head_version=str(head["head_version"]))
                self._advance_task(h, ctx, snap["body"].get("task_ref"), "approval.superseded")
                h.audit("approval.superseded", {"approval_id": approval_id,
                    "snapshot_digest": snap["digest"]}, object_refs=[ref.to_dict()])
                refs.append(ref)
            h.outcome.object_refs = tuple(refs)
        receipt = UnitOfWork(self.store, assessment, "approval.validity").execute(cb)
        if receipt.status == "rejected":
            raise KernelError(receipt.error)
        return receipt

    def _execution_mode_problem(self, body: Mapping[str, Any]) -> BlockError | None:
        if body["evidence_mode"] != "production":
            return None
        attempt = self._exact_revision(body["selected_attempt_ref"], kind="attempt")["payload"]
        packet = self._exact_revision(body["packet_ref"], kind="execution_packet")["payload"]
        if attempt.get("mode") != "production" or packet.get("mode") != "production":
            return verification_failed("production delivery requires a production attempt and execution packet")
        return None

    def _evidence_problem(self, body: Mapping[str, Any]) -> BlockError | None:
        """A snapshot may only be requested/applied while its evidence is a
        current, passed verification bound to the same candidate."""
        mode_problem = self._execution_mode_problem(body)
        if mode_problem is not None:
            return mode_problem
        if self.artifact_storage is None:
            return capability_unavailable("artifact storage must be configured for delivery")
        for artifact in self._required_artifact_refs(body):
            try:
                self.artifact_storage.require_ready((artifact,))
            except KernelError as exc:
                return exc.error
        for ref_dict in body.get("verification_refs", ()):
            ref = ObjectRef.from_dict(ref_dict)
            state = self._verification_state(ref)
            if state is None:
                return evidence_stale(f"verification {ref.object_id} not found")
            if not state.get("passed"):
                return verification_failed(
                    f"verification {ref.object_id} is {state.get('result')}, not passed")
            if state.get("validity") != "current":
                return evidence_stale(f"verification {ref.object_id} is {state.get('validity')}")
            if state.get("candidate_digest") != body.get("candidate_digest"):
                return evidence_stale(
                    f"verification {ref.object_id} belongs to another candidate")
        return None

    def _advance_task(self, h, ctx: CommandContext, task_ref: Mapping[str, Any] | None,
                      command: str) -> None:
        if not task_ref:
            return
        object_id = task_ref.get("object_id")
        if not object_id:
            return
        self._advance_task_id(h, object_id, command, strict=True)

    def _advance_task_id(self, h, task_id: str, command: str, *, strict: bool) -> bool:
        payload, head = self._head_payload("task", task_id)
        if payload is None or head is None:
            return False
        if head["updated_seq"] == h.records.commit_seq:
            # this transaction already published a task revision (head_history has
            # one row per pointer per commit_seq)
            return False
        start_phase = payload.get("phase")
        phase = start_phase
        target: str | None = None
        facts: dict[str, bool] | None = None
        for _ in range(6):
            transition = flow.task_transition(phase, command)
            if not isinstance(transition, flow.Rejection):
                target = transition.to_state
                break
            # the task phase index can lag behind facts other services already
            # persisted; catch up only
            # along a legal, fact-backed path -- never a generic setStatus
            if facts is None:
                facts = self._task_facts(task_id)
            if phase == "dispatch_ready" and facts["attempt"]:
                phase = "executing"
            elif phase == "executing" and facts["verification"]:
                phase = "verifying"
            else:
                # delivery_ready is a real selection decision, never inferred
                break
        if target is None:
            if strict:
                raise KernelError(flow.task_transition(start_phase, command).error)
            return False
        if target == start_phase:
            return False
        new = h.records.append_revision("task", task_id,
                                        {**payload, "phase": target}, "task.v1")
        h.records.publish_head(new, "current", expected_head_version=str(head["head_version"]))
        return True

    def _task_facts(self, task_id: str) -> dict[str, bool]:
        attempts: set[str] = set()
        for attempt_id in self._attempt_heads():
            rows = self.store.conn.execute(
                "SELECT payload_json FROM revision WHERE type='attempt' AND object_id=?"
                " ORDER BY ordinal", (attempt_id,)).fetchall()
            for row in rows:
                ref = json.loads(row[0]).get("task_ref")
                if isinstance(ref, Mapping) and ref.get("object_id") == task_id:
                    attempts.add(attempt_id)
                    break
        verification = False
        if attempts:
            rows = self.store.conn.execute(
                "SELECT payload_json FROM revision WHERE type='verification'").fetchall()
            for row in rows:
                payload = json.loads(row[0])
                if (payload.get("attempt_ref") or {}).get("object_id") in attempts:
                    verification = True
                    break
        return {"attempt": bool(attempts), "verification": verification}

    def _attempt_task_id(self, attempt_ref: ObjectRef) -> str | None:
        payload, _ = self._head_payload(attempt_ref.object_type, attempt_ref.object_id)
        if payload is None:
            rev = self.store.get_revision(attempt_ref)
            payload = rev["payload"] if rev else None
        ref = (payload or {}).get("task_ref")
        if isinstance(ref, Mapping) and ref.get("object_id"):
            return ref["object_id"]
        # the settle revision may not repeat task_ref; the first revision binds it
        rows = self.store.conn.execute(
            "SELECT payload_json FROM revision WHERE type='attempt' AND object_id=?"
            " ORDER BY ordinal", (attempt_ref.object_id,)).fetchall()
        for row in rows:
            ref = json.loads(row[0]).get("task_ref")
            if isinstance(ref, Mapping) and ref.get("object_id"):
                return ref["object_id"]
        return None

    # ------------------------------------------------------------- selection
    def select_attempt(self, ctx: CommandContext, attempt_ref: Any, comparison_refs: Iterable[Any],
                       purpose: str, reason: str) -> CommandReceipt:
        """Record the selection decision; a delivery selection needs a current
        passed verification, a knowledge-only selection is explicitly separate."""
        attempt = ObjectRef.from_dict(attempt_ref) if isinstance(attempt_ref, Mapping) else attempt_ref
        comparisons = [self._ref_dict(r) for r in comparison_refs]

        def cb(h):
            self._require(CAP_VERIFICATION, ctx)
            if purpose not in ("delivery", "knowledge"):
                raise KernelError(invalid_input(f"unknown selection purpose {purpose!r}"))
            if not reason:
                raise KernelError(invalid_input("attempt.select requires a reason"))
            if not comparisons:
                raise KernelError(invalid_input("attempt.select requires comparison refs"))
            selected=self._exact_revision(attempt.to_dict(),kind="attempt")["payload"]
            for comparison in comparisons:
                other=self._exact_revision(comparison,kind="attempt")["payload"]
                if not self._same_object(other.get("task_ref"),selected["task_ref"]):
                    raise KernelError(invalid_input("comparison attempts belong to different tasks"))
            if purpose=="delivery" and selected.get("status")!="completed":
                raise KernelError(verification_failed("delivery requires a completed attempt"))
            verification_refs: list[dict[str, Any]] = []
            if purpose == "delivery":
                for report_id, payload in self._passed_reports_for(attempt.object_id):
                    verification_refs.append(
                        ObjectRef(self.store.project_id, "verification", report_id,
                                  payload["revision_id"]).to_dict())
                if not verification_refs:
                    raise KernelError(verification_failed(
                        "no current passed verification for the selected attempt"))
            selection_id = _new_id("selection")
            body = {"selection_id": selection_id, "attempt_ref": attempt.to_dict(),
                    "comparison_refs": comparisons, "purpose": purpose, "reason": reason,
                    "verification_refs": verification_refs,
                    "decided_by": ctx.scope.principal_id, "decided_seq": h.records.commit_seq}
            r = h.records.append_revision("selection", selection_id, body, "selection.v1")
            h.records.publish_head(r, "current")
            task_id = self._attempt_task_id(attempt)
            if task_id:
                self._advance_task_id(h, task_id, "attempt.select", strict=False)
            h.audit("attempt.selected", payload={"selection_id": selection_id,
                                                 "purpose": purpose,
                                                 "attempt_id": attempt.object_id},
                    object_refs=[r.to_dict()])
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "attempt.select").execute(cb)

    def _passed_reports_for(self, attempt_id: str) -> list[tuple[str, dict[str, Any]]]:
        found: list[tuple[str, dict[str, Any]]] = []
        rows = self.store.conn.execute(
            "SELECT object_id FROM entity_head WHERE type='verification' AND pointer_name='current'"
        ).fetchall()
        for (report_id,) in rows:
            payload, head = self._head_payload("verification", report_id)
            if not payload or not head:
                continue
            if not payload.get("passed") or payload.get("validity") != "current":
                continue
            if (payload.get("attempt_ref") or {}).get("object_id") != attempt_id:
                continue
            found.append((report_id, {**payload, "revision_id": head["revision_id"]}))
        return found

    def _exact_revision(self, raw: Mapping[str, Any], *, kind: str | None = None) -> dict[str, Any]:
        ref = ObjectRef.from_dict(raw)
        self._in_project(ref, "snapshot reference")
        if kind is not None and ref.object_type != kind:
            raise KernelError(invalid_input(f"expected {kind} revision"))
        row = self.store.get_revision(ref)
        if row is None:
            raise KernelError(reference_not_found(
                f"{ref.object_type}/{ref.object_id}@{ref.revision_id} not found"))
        return row

    @staticmethod
    def _same_object(left: Mapping[str, Any] | None, right: Mapping[str, Any]) -> bool:
        return left is not None and all(left.get(key) == right.get(key)
                                        for key in ("project_id", "object_type", "object_id"))

    def _validate_snapshot_references(self, body: Mapping[str, Any]) -> dict[str, str]:
        """Resolve pinned evidence and its relationships before any snapshot commit."""
        digests: dict[str, str] = {}
        for raw in delivery_rules.iter_refs(body):
            row = self._exact_revision(raw)
            key = ":".join(raw[name] for name in
                           ("project_id", "object_type", "object_id", "revision_id"))
            digests[key] = row["digest"]
            current, _ = self._head_payload(raw["object_type"], raw["object_id"])
            if raw["object_type"] != "task" and current is not None:
                if delivery_rules.decisive_projection(raw["object_type"], current) != \
                        delivery_rules.decisive_projection(raw["object_type"], row["payload"]):
                    raise KernelError(evidence_stale("pinned decisive revision is no longer current"))
        self._exact_revision(body["task_ref"], kind="task")
        attempt = self._exact_revision(body["selected_attempt_ref"], kind="attempt")["payload"]
        packet = self._exact_revision(body["packet_ref"], kind="execution_packet")["payload"]
        mode_problem = self._execution_mode_problem(body)
        if mode_problem is not None:
            raise KernelError(mode_problem)
        if (not self._same_object(attempt.get("task_ref"), body["task_ref"])
                or not self._same_object(packet.get("task_ref"), body["task_ref"])
                or attempt.get("packet_ref") != body["packet_ref"]):
            raise KernelError(invalid_input("snapshot task, attempt and packet are unrelated"))
        for name in ("requirement_refs", "acceptance_refs", "rule_refs", "design_refs"):
            if name in packet and packet[name] != body[name]:
                raise KernelError(invalid_input(f"snapshot {name} differs from its execution packet"))
        for name in ("scope_ref", "input_manifest_ref", "context_manifest_ref", "environment_ref"):
            if name in packet and packet[name] != body[name]:
                raise KernelError(invalid_input(f"snapshot {name} differs from its execution packet"))
        if not body.get("verification_refs"):
            raise KernelError(required_fact_unknown("snapshot needs verified evidence"))
        for raw in body["verification_refs"]:
            report = self._exact_revision(raw, kind="verification")["payload"]
            if (report.get("attempt_ref") != body["selected_attempt_ref"]
                    or report.get("candidate_digest") != body["candidate_digest"]
                    or report.get("evidence_mode") != body["evidence_mode"]):
                raise KernelError(evidence_stale("verification does not bind this snapshot candidate"))
            candidate = self._exact_revision(report["candidate_manifest_ref"],
                                             kind="candidate_manifest")["payload"]
            if candidate.get("candidate_digest") != body["candidate_digest"]:
                raise KernelError(artifact_digest_mismatch("candidate digest differs from snapshot"))
            if sorted(candidate.get("artifacts", []), key=lambda a: a["artifact_id"]) != \
                    sorted(body["artifacts"], key=lambda a: a["artifact_id"]):
                raise KernelError(artifact_digest_mismatch("snapshot artifacts differ from candidate"))
            if report.get("acceptance_refs") != body["acceptance_refs"]:
                raise KernelError(evidence_stale("verification acceptance differs from snapshot"))
        problem = self._evidence_problem(body)
        if problem is not None:
            raise KernelError(problem)
        selections = self.store.conn.execute(
            "SELECT object_id FROM entity_head WHERE type='selection' AND pointer_name='current'"
        ).fetchall()
        if not any((selection := self._head_payload("selection", row[0])[0])
                   and selection.get("purpose") == "delivery"
                   and selection.get("attempt_ref") == body["selected_attempt_ref"]
                   and all(ref in selection.get("verification_refs", [])
                           for ref in body["verification_refs"]) for row in selections):
            raise KernelError(required_fact_unknown("snapshot has no matching delivery selection"))
        return digests

    def delivery_request(self, ctx: CommandContext, payload: Mapping[str, Any]) -> CommandReceipt:
        from ..design.references import checked_payload, current, exact
        def cb(h):
            self._require(CAP_DISPATCH,ctx)
            data=checked_payload("delivery.request",payload)
            selection_ref,selection_row=current(self.store,data["selection_ref"],"selection")
            selection=selection_row["payload"]
            if selection.get("purpose")!="delivery":
                raise KernelError(invalid_input("selection is not for delivery"))
            attempt_ref,attempt_row=exact(self.store,selection["attempt_ref"],"attempt")
            attempt=attempt_row["payload"]
            _,packet_row=exact(self.store,attempt["packet_ref"],"execution_packet")
            packet=packet_row["payload"]
            candidate_ref,candidate_row=current(self.store,data["candidate_ref"],"candidate_manifest")
            candidate=candidate_row["payload"]
            _,target_row=current(self.store,data["target_ref"],"delivery_target")
            if target_row["payload"].get("method")!="bundle":
                raise KernelError(capability_unavailable("only bundle delivery is configured"))
            refs=[]
            for raw in selection["verification_refs"]:
                _,report=exact(self.store,raw,"verification")
                if report["payload"].get("candidate_manifest_ref")==candidate_ref.to_dict():
                    refs.append(raw)
            if not refs:
                raise KernelError(verification_failed("selected verification does not bind this candidate"))
            oid="request-"+sha256_digest({"principal":ctx.scope.principal_id,"key":ctx.idempotency_key})[:20]
            scope_ref=h.records.append_revision("scope",oid,packet["scope"],"scope.v1")
            input_ref=h.records.append_revision("input_manifest",oid,
                {"base_content_digest":packet["base_content_digest"],"dependency_refs":packet["dependency_refs"]},"input_manifest.v1")
            context_ref=h.records.append_revision("context_manifest",oid,
                {"requirement_refs":packet["requirement_refs"],"design_ref":packet["design_ref"],
                 "budget_ref":packet["budget_ref"]},"context_manifest.v1")
            body={"schema_version":"1.0.0","canonicalization":"rfc8785","project_id":self.store.project_id,
                "evidence_mode":ctx.scope.mode,"task_ref":packet["task_ref"],
                "selected_attempt_ref":attempt_ref.to_dict(),"packet_ref":attempt["packet_ref"],
                "requirement_refs":packet["requirement_refs"],"design_refs":[packet["design_ref"]],
                "acceptance_refs":packet["acceptance_refs"],"rule_refs":packet["rule_refs"],
                "scope_ref":scope_ref.to_dict(),"input_manifest_ref":input_ref.to_dict(),
                "context_manifest_ref":context_ref.to_dict(),"environment_ref":packet["environment_ref"],
                "verification_refs":refs,"candidate_digest":candidate["candidate_digest"],
                "delivery":{"method":"bundle","target_ref":data["target_ref"]},
                "artifacts":candidate["artifacts"]}
            self._freeze_snapshot(h,ctx,oid,body)
            frozen=h.outcome.object_refs[0]
            self._request_approval(h,ctx,"approval-"+oid,oid,sha256_digest(body),expires_at=None)
            h.outcome.object_refs=(*h.outcome.object_refs,frozen)
        return UnitOfWork(self.store,ctx,"delivery.request").execute(cb)

    def delivery_apply(self, ctx: CommandContext, payload: Mapping[str, Any]) -> CommandReceipt:
        from ..design.references import checked_payload
        self._require(CAP_DELIVERY,ctx)
        data=checked_payload("delivery.apply",payload)
        approval,_=self._head_payload("approval",data["approval_id"])
        if approval is None:
            raise KernelError(reference_not_found("approval not found"))
        return self.apply_delivery(ctx,data["approval_id"],approval["snapshot_id"],data["snapshot_digest"])

    # ------------------------------------------------------- freeze snapshot
    def _freeze_snapshot(self, h, ctx, snapshot_id, body):
        self._require(CAP_DISPATCH, ctx)
        try:
            validate_delivery_snapshot_body(body)
        except ValidationError as exc:
            raise KernelError(exc.error) from exc
        if body.get("project_id") != ctx.scope.project_id:
            raise KernelError(scope_mismatch("snapshot body belongs to another project"))
        digest = sha256_digest(body)
        existing = self._snapshot(snapshot_id)
        if existing is not None:
            if existing["digest"] != digest:
                raise KernelError(_snapshot_changed(
                    f"snapshot {snapshot_id} is already frozen with another digest"))
            head = self.store.get_head("delivery_snapshot", snapshot_id, "current")
            h.outcome.object_refs = (ObjectRef(self.store.project_id, "delivery_snapshot",
                                               snapshot_id, head["revision_id"]),)
            return
        reference_digests = self._validate_snapshot_references(body)
        basis = self._basis(body)
        required = self._required_artifact_refs(body)
        if required and self.artifact_storage is None:
            raise KernelError(capability_unavailable("required artifact verification is unavailable"))
        if required:
            # required artifact missing/unready/digest-changed -> never freeze
            self.artifact_storage.require_ready(required)
        payload = {"snapshot_id": snapshot_id, "body": body, "digest": digest,
                   "status": "frozen", "evidence_mode": body["evidence_mode"],
                   "reference_digests": reference_digests,
                   "eligibility_basis": basis, "basis_digest": sha256_digest(basis),
                   "created_seq": h.records.commit_seq}
        r = h.records.append_revision("delivery_snapshot", snapshot_id, payload,
                                      "delivery_snapshot.v1")
        h.records.publish_head(r, "current")
        h.audit("delivery_snapshot.frozen",
                payload={"snapshot_id": snapshot_id, "digest": digest},
                object_refs=[r.to_dict()])
        h.outcome.object_refs = (r,)

    def freeze_snapshot(self, ctx: CommandContext, snapshot_id: str,
                        body: dict[str, Any]) -> CommandReceipt:
        def cb(h):
            self._freeze_snapshot(h, ctx, snapshot_id, body)
        return UnitOfWork(self.store, ctx, "delivery.request").execute(cb)

    # ------------------------------------------------------ request approval
    def _request_approval(self, h, ctx, approval_id, snapshot_id, snapshot_digest, *, expires_at=None):
        self._require(CAP_DISPATCH, ctx)
        snap = self._snapshot(snapshot_id)
        if snap is None:
            raise KernelError(reference_not_found("snapshot not found"))
        if snap["digest"] != snapshot_digest:
            raise KernelError(_snapshot_changed("snapshot digest mismatch"))
        if not self._snapshot_eligible(snap):
            raise KernelError(_snapshot_changed(
                "decisive inputs changed since the snapshot was frozen"))
        problem = self._evidence_problem(snap["body"])
        if problem is not None:
            raise KernelError(problem)
        for other in self._approval_heads():
            payload, _ = self._head_payload("approval", other)
            if (payload and payload.get("snapshot_digest") == snapshot_digest
                    and payload.get("status") == ApprovalStatus.PENDING.value):
                # same snapshot -> return the active request, never a duplicate
                head = self.store.get_head("approval", other, "current")
                h.outcome.object_refs = (ObjectRef(self.store.project_id, "approval", other,
                                                   head["revision_id"]),)
                return
        payload = {"approval_id": approval_id, "snapshot_id": snapshot_id,
                   "snapshot_digest": snapshot_digest, "status": ApprovalStatus.PENDING.value,
                   "requested_by": ctx.scope.principal_id, "requested_seq": h.records.commit_seq,
                   "expires_at": expires_at, "apply_started": False, "operation_id": None}
        r = h.records.append_revision("approval", approval_id, payload, "approval.v1")
        h.records.publish_head(r, "current")
        self._advance_task(h, ctx, snap["body"].get("task_ref"), "delivery.request")
        h.audit("approval.requested", payload={"approval_id": approval_id,
                                               "snapshot_digest": snapshot_digest},
                object_refs=[r.to_dict()])
        h.outcome.object_refs = (r,)

    def request_approval(self, ctx: CommandContext, approval_id: str, snapshot_id: str,
                         snapshot_digest: str, *, expires_at: str | None = None) -> CommandReceipt:
        def cb(h):
            self._request_approval(h, ctx, approval_id, snapshot_id, snapshot_digest, expires_at=expires_at)
        return UnitOfWork(self.store, ctx, "delivery.request").execute(cb)

    # -------------------------------------------------------- approval decide
    def decide_approval(self, ctx: CommandContext, approval_id: str, decision: str,
                        snapshot_digest: str, *, is_human: bool, reason: str = "") -> CommandReceipt:
        replay = UnitOfWork(self.store, ctx, "approval.decide")._check_idempotency()
        if replay is not None:
            return replay
        if is_human and ctx.scope.has(CAP_APPROVAL):
            self.refresh_approvals(ctx)
        payload, _ = self._head_payload("approval", approval_id)
        if payload is None:
            raise KernelError(reference_not_found("approval not found"))
        if (payload.get("status") == ApprovalStatus.PENDING.value
                and _expired_at(payload.get("expires_at"))):
            self._mark_expired(ctx, approval_id)
            raise KernelError(approval_invalid("approval expired"))

        def cb(h):
            self._require_human(is_human)
            self._require(CAP_APPROVAL, ctx)
            current, cur_head = self._head_payload("approval", approval_id)
            if current is None or cur_head is None:
                raise KernelError(reference_not_found("approval not found"))
            if current.get("snapshot_digest") != snapshot_digest:
                raise KernelError(approval_invalid("snapshot digest mismatch"))
            snap = self._snapshot(current["snapshot_id"])
            eligible = snap is not None and self._snapshot_eligible(snap)
            if current.get("status") == ApprovalStatus.SUPERSEDED.value and not eligible:
                raise KernelError(_snapshot_changed("decisive inputs changed since the snapshot was frozen"))
            t = flow.approval_transition(current.get("status"), decision, is_human=is_human,
                                         snapshot_eligible=eligible)
            if isinstance(t, flow.Rejection):
                raise KernelError(t.error)
            new = {**current, "status": t.to_state, "decision": decision,
                   "decided_by": ctx.scope.principal_id, "decided_human": True,
                   "decided_at": _utc_now(), "decision_reason": reason,
                   "decision_seq": h.records.commit_seq}
            r = h.records.append_revision("approval", approval_id, new, "approval.v1")
            h.records.publish_head(r, "current", expected_head_version=str(cur_head["head_version"]))
            if snap is not None and t.to_state == ApprovalStatus.APPROVED.value:
                self._advance_task(h, ctx, snap["body"].get("task_ref"), "approval.approved")
            elif snap is not None and t.to_state == ApprovalStatus.REJECTED.value:
                self._advance_task(h, ctx, snap["body"].get("task_ref"), "approval.rejected")
            h.audit("approval.decided", payload={"approval_id": approval_id, "decision": decision,
                                                 "snapshot_digest": snapshot_digest},
                    object_refs=[r.to_dict()])
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "approval.decide").execute(cb)

    # ------------------------------------------------------- decision.record
    def decision_record(self, ctx: CommandContext, payload: Mapping[str, Any],
                        *, is_human: bool) -> CommandReceipt:
        """Record the human decision that authorizes restore/share/export.

        Design 04 §9: human only, and the action decides which capability is
        required (restore.apply→project.admin, knowledge.promote→knowledge.share,
        dataset.export→dataset.export); the subject digest and target scope must
        match, and a delivery approval can never stand in for these decisions.
        """
        action = payload["action"]
        subject_kind = payload["subject_kind"]
        target_scope = payload["target_scope"]
        expected = DECISION_ACTIONS.get(action)
        if expected is None:
            raise KernelError(invalid_input(f"action {action!r} has no human decision"))

        def cb(h):
            self._require_human(is_human)
            kind, capability = expected
            if subject_kind != kind:
                raise KernelError(invalid_input(
                    f"subject_kind {subject_kind!r} does not match action {action!r}"))
            self._require(capability, ctx)
            if subject_kind == "dataset_export":
                if target_scope != "approved_export_sink":
                    raise KernelError(invalid_input(
                        "dataset.export decisions target an approved export sink"))
            elif target_scope == "approved_export_sink":
                raise KernelError(invalid_input(
                    f"action {action!r} may not target an export sink"))
            subject_ref = ObjectRef.from_dict(payload["subject_ref"])
            self._in_project(subject_ref, "decision subject")
            row = self.store.get_revision(subject_ref)
            if row is None:
                raise KernelError(reference_not_found(
                    f"decision subject {subject_ref.object_type}/{subject_ref.object_id}"
                    f"@{subject_ref.revision_id} not found"))
            if row["digest"] != payload["subject_digest"]:
                raise KernelError(artifact_digest_mismatch(
                    "decision subject digest does not match the stored revision"))
            target_ref = ObjectRef.from_dict(payload["target_ref"])
            self._in_project(target_ref, "decision target")
            target = self.store.get_revision(target_ref)
            if target is None:
                raise KernelError(reference_not_found(
                    "decision target description is not a stored revision"))
            if subject_kind == "dataset_export":
                if subject_ref.object_type != "dataset_review":
                    raise KernelError(invalid_input("export subject must be a reviewed dataset"))
                if (target["payload"].get("target_scope") != target_scope
                        or not target["payload"].get("sink_id")):
                    raise KernelError(invalid_input("export target must describe the approved sink"))
            record = {
                "decision_id": payload.get("decision_id") or f"dec-{uuid.uuid4().hex[:12]}",
                "subject_kind": subject_kind,
                "subject_ref": subject_ref.to_dict(),
                "subject_digest": payload["subject_digest"],
                "action": action,
                "target_scope": target_scope,
                "target_ref": target_ref.to_dict(),
                "decision": payload["decision"],
                "reason": payload["reason"],
                "is_human": True,
                "decided_by": ctx.scope.principal_id,
                "decided_seq": h.records.commit_seq,
            }
            r = h.records.append_revision("decision", record["decision_id"], record,
                                          "p04.decision.v1")
            h.records.publish_head(r, "current")
            h.outcome.object_refs = (r,)
            h.outcome.operation_id = record["decision_id"]
            h.audit("decision.recorded",
                    payload={"decision_id": record["decision_id"], "action": action,
                             "decision": payload["decision"], "target_scope": target_scope},
                    object_refs=[r.to_dict()])
        return UnitOfWork(self.store, ctx, "decision.record").execute(cb)

    def _in_project(self, ref: ObjectRef, what: str) -> None:
        if ref.project_id != self.store.project_id:
            raise KernelError(scope_mismatch(f"{what} belongs to another project"))

    # --------------------------------------------------------- approval revoke
    def approval_revoke(self, ctx: CommandContext, approval_id: str, snapshot_digest: str, *,
                        is_human: bool, reason: str = "") -> CommandReceipt:
        payload, _ = self._head_payload("approval", approval_id)
        if payload is None:
            raise KernelError(reference_not_found("approval not found"))
        if (payload.get("status") == ApprovalStatus.PENDING.value
                and _expired_at(payload.get("expires_at"))):
            self._mark_expired(ctx, approval_id)
            raise KernelError(approval_invalid("approval expired"))

        def cb(h):
            self._require_human(is_human)
            self._require(CAP_APPROVAL, ctx)
            if not reason:
                raise KernelError(invalid_input("approval.revoke requires a reason"))
            current, cur_head = self._head_payload("approval", approval_id)
            if current is None or cur_head is None:
                raise KernelError(reference_not_found("approval not found"))
            if current.get("snapshot_digest") != snapshot_digest:
                raise KernelError(_snapshot_changed(
                    "approval is bound to another snapshot digest"))
            t = flow.revoke_approval(current.get("status"), is_human=is_human,
                                     apply_started=bool(current.get("apply_started")))
            if isinstance(t, flow.Rejection):
                raise KernelError(t.error)
            new = {**current, "status": t.to_state, "revoke_reason": reason,
                   "revoked_by": ctx.scope.principal_id, "revoked_at": _utc_now()}
            r = h.records.append_revision("approval", approval_id, new, "approval.v1")
            h.records.publish_head(r, "current", expected_head_version=str(cur_head["head_version"]))
            snap = self._snapshot(current["snapshot_id"])
            if snap is not None:
                command = {"superseded": "approval.superseded",
                           "revoked": "approval.revoked"}.get(t.to_state)
                if command is not None:
                    self._advance_task(h, ctx, snap["body"].get("task_ref"), command)
            h.audit("approval.revoked", payload={"approval_id": approval_id, "status": t.to_state,
                                                 "reason": reason},
                    object_refs=[r.to_dict()])
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "approval.revoke").execute(cb)

    def _mark_expired(self, ctx: CommandContext, approval_id: str) -> None:
        exp_ctx = self._derive(ctx, f"expire:{approval_id}", approval_id)

        def cb(h):
            current, head = self._head_payload("approval", approval_id)
            if current is None or head is None:
                return
            if current.get("status") != ApprovalStatus.PENDING.value:
                return
            new = {**current, "status": ApprovalStatus.EXPIRED.value, "expired_at": _utc_now()}
            r = h.records.append_revision("approval", approval_id, new, "approval.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            snap = self._snapshot(current["snapshot_id"])
            if snap is not None:
                self._advance_task(h, ctx, snap["body"].get("task_ref"), "approval.expired")
            h.outcome.object_refs = (r,)
        UnitOfWork(self.store, exp_ctx, "approval.decide").execute(cb)

    # ----------------------------------------------------------- verification
    def verification_run(self, ctx: CommandContext, attempt_ref: ObjectRef,
                         candidate_manifest_ref: ObjectRef,
                         acceptance_items: list[Any] | None = None,
                         check_results: list[Any] | None = None, *,
                         acceptance_refs: Iterable[Any] = (),
                         check_provider: Callable[[list[AcceptanceItem]], list[Any]] | None = None,
                         evidence_mode: str = "production",
                         human_attested_check_ids: Iterable[str] = ()) -> CommandReceipt:
        """Run the declared checks and persist an immutable report revision.

        A declared ``human_review`` item without a trusted human submission makes
        the report ``incomplete``; nothing is ever upgraded to passed by absence.
        """
        self._require(CAP_VERIFICATION, ctx)
        acceptance_refs=tuple(acceptance_refs)
        prepared_checks=list(check_results or [])
        provider_basis=None
        verification_operation_id=None
        if check_provider is not None:
            replay=UnitOfWork(self.store,ctx,"verification.run")._check_idempotency()
            if replay is not None:
                return replay
            items=self._resolve_items(list(acceptance_items or []),list(acceptance_refs))
            self._exact_revision(attempt_ref.to_dict(),kind="attempt")
            candidate=self._exact_revision(candidate_manifest_ref.to_dict(),kind="candidate_manifest")
            provider_basis=sha256_digest({"items":flow.acceptance_basis(items),"candidate":candidate["digest"]})
            from ...data.queries.service import QueryService
            for old in QueryService(self.store).latest_revisions("verification"):
                old_candidate = old["payload"].get("candidate_manifest_ref", {})
                if old_candidate.get("object_id") == candidate_manifest_ref.object_id:
                    old_ref = ObjectRef(self.store.project_id,"verification",old["object_id"],old["revision_id"])
                    self.check_validity(self._derive(ctx,"validity:"+old["object_id"],
                        {"basis":provider_basis}),old_ref)
            verification_operation_id="verify-"+sha256_digest({"principal":ctx.scope.principal_id,"key":ctx.idempotency_key})[:20]
            def claim_cb(h):
                r=h.records.append_revision("verification_operation",verification_operation_id,
                    {"operation_id":verification_operation_id,"status":"running","basis_digest":provider_basis,
                     "attempt_ref":attempt_ref.to_dict(),"candidate_manifest_ref":candidate_manifest_ref.to_dict(),
                     "acceptance_refs":[self._ref_dict(ref) for ref in acceptance_refs]},
                    "verification_operation.v1")
                h.records.publish_head(r,"current")
                h.outcome.object_refs=(r,)
                h.outcome.operation_id=verification_operation_id
            claim=UnitOfWork(self.store,self._derive(ctx,"verify-claim",{"input_hash":ctx.input_hash}),"verification.claim")
            claimed=claim.execute(claim_cb)
            if claimed.status!="accepted" or not claim.did_commit:
                return claimed
            try:
                if hasattr(check_provider,"run"):
                    prepared_checks.extend(check_provider.run(ctx.scope,attempt_ref,candidate_manifest_ref,acceptance_refs))
                else:
                    prepared_checks.extend(check_provider(items) or ())
            except Exception as exc:
                self._verification_operation_outcome(ctx,verification_operation_id,"unknown",
                    {"type":type(exc).__name__,"message":str(exc)})
                raise KernelError(required_fact_unknown("verification provider failed; inspect operation.status before a new run")) from exc
        def cb(h):
            self._require(CAP_VERIFICATION, ctx)
            self._exact_revision(attempt_ref.to_dict(),kind="attempt")
            candidate=self._exact_revision(candidate_manifest_ref.to_dict(),kind="candidate_manifest")
            items = self._resolve_items(list(acceptance_items or []), list(acceptance_refs))
            if provider_basis is not None and provider_basis != sha256_digest({"items":flow.acceptance_basis(items),"candidate":candidate["digest"]}):
                raise KernelError(evidence_stale("verification inputs changed while provider ran"))
            if not items:
                raise KernelError(required_fact_unknown(
                    "verification has no acceptance items to check"))
            checks = self._resolve_checks(prepared_checks, items, None)
            attested = set(human_attested_check_ids)

            cand_payload, cand_head = self._head_payload(candidate_manifest_ref.object_type,
                                                         candidate_manifest_ref.object_id)
            candidate_digest = (cand_payload or {}).get("candidate_digest") or \
                (cand_payload or {}).get("digest") or candidate_manifest_ref.revision_id
            stale_candidate = (cand_head is not None
                               and cand_head["revision_id"] != candidate_manifest_ref.revision_id)
            outcome = flow.evaluate_verification(
                items, checks, evidence_mode=evidence_mode,
                expected_candidate_digest=candidate_digest,
                human_attested_check_ids=attested)
            reasons = list(outcome.reasons)
            incomplete = list(outcome.incomplete_reasons)
            stale_acceptance = any(
                (self.store.get_head(ref["object_type"],ref["object_id"],"current") or {}).get("revision_id") != ref["revision_id"]
                for ref in (self._ref_dict(raw) for raw in acceptance_refs))
            if stale_candidate or stale_acceptance:
                reason="stale candidate manifest" if stale_candidate else "stale acceptance revision"
                reasons.append(reason)
                incomplete.append(reason)
                outcome = flow.VerificationOutcome("incomplete", False, tuple(reasons),
                                                   tuple(incomplete))

            report_id = _new_id("verification")
            payload = {
                "verification_id": report_id,
                "attempt_ref": attempt_ref.to_dict(),
                "candidate_manifest_ref": candidate_manifest_ref.to_dict(),
                "candidate_digest": candidate_digest,
                "acceptance_refs": [self._ref_dict(r) for r in acceptance_refs],
                "acceptance_basis": flow.acceptance_basis(items),
                "checks": [self._check_dict(c) for c in checks],
                "human_attested_check_ids": sorted(attested),
                "evidence_mode": evidence_mode,
                "result": outcome.status, "passed": outcome.passed,
                "validity": "current", "complete": outcome.complete,
                "reasons": reasons,
                "incomplete_reasons": list(outcome.incomplete_reasons),
                "created_seq": h.records.commit_seq,
            }
            r = h.records.append_revision("verification", report_id, payload, "verification.v1")
            h.records.publish_head(r, "current")
            task_id = self._attempt_task_id(attempt_ref)
            if task_id:
                # one task revision per transaction: the run moves the task to
                # verifying; attempt.select later publishes delivery_ready
                self._advance_task_id(h, task_id, "verification.run", strict=False)
            h.audit("verification.recorded",
                    payload={"verification_id": report_id, "result": outcome.status},
                    object_refs=[r.to_dict()])
            h.outcome.object_refs = (r,)
            if verification_operation_id is not None:
                prior,head=self._head_payload("verification_operation",verification_operation_id)
                op=h.records.append_revision("verification_operation",verification_operation_id,
                    {**prior,"status":"succeeded","verification_ref":r.to_dict(),"result":outcome.status},
                    "verification_operation.v1")
                h.records.publish_head(op,"current",str(head["head_version"]))
                h.outcome.operation_id=verification_operation_id
        receipt=UnitOfWork(self.store, ctx, "verification.run").execute(cb)
        if receipt.status=="rejected" and verification_operation_id is not None:
            self._verification_operation_outcome(ctx,verification_operation_id,"failed",receipt.error.to_dict())
        return receipt

    def _verification_operation_outcome(self,ctx,operation_id,status,error):
        def cb(h):
            prior,head=self._head_payload("verification_operation",operation_id)
            if prior["status"]!="running":
                return
            r=h.records.append_revision("verification_operation",operation_id,
                {**prior,"status":status,"error":error},"verification_operation.v1")
            h.records.publish_head(r,"current",str(head["head_version"]))
            h.outcome.object_refs=(r,)
        UnitOfWork(self.store,self._derive(ctx,"verify-outcome",{"status":status,"error":error}),
                   "verification.outcome").execute(cb)

    def record_review(self, ctx: CommandContext, verification_ref: ObjectRef, check_id: str,
                      candidate_digest: str, result: str, evidence_refs: Iterable[Any],
                      reason: str, *, is_human: bool) -> CommandReceipt:
        """Trusted-human check submission.

        Appends a new report revision bound to the action/candidate/reason and
        leaves the previous report revision untouched.
        """
        evidence = [self._ref_dict(r) for r in evidence_refs]

        def cb(h):
            self._require_human(is_human)
            self._require(CAP_VERIFICATION, ctx)
            if result not in ("pass", "fail"):
                raise KernelError(invalid_input(f"unknown review result {result!r}"))
            if not evidence:
                raise KernelError(invalid_input("record_review requires evidence_refs"))
            if not reason:
                raise KernelError(invalid_input("record_review requires a reason"))
            current, head = self._head_payload(verification_ref.object_type,
                                              verification_ref.object_id)
            if current is None or head is None:
                raise KernelError(reference_not_found("verification report not found"))
            if current.get("candidate_digest") != candidate_digest:
                raise KernelError(evidence_stale(
                    "review candidate digest does not match the report"))
            item = self._find_item(current, check_id)
            if item is None:
                raise KernelError(reference_not_found(
                    f"no declared acceptance item {check_id} in this report"))
            human = CheckResult(check_id=check_id,
                                recipe_ref=ObjectRef.from_dict(item["recipe_ref"]),
                                candidate_digest=candidate_digest, result=result,
                                evidence_refs=tuple(ObjectRef.from_dict(r) for r in evidence),
                                evidence_mode=current.get("evidence_mode", "production"))
            attested = set(current.get("human_attested_check_ids", [])) | {check_id}
            checks = [c for c in current.get("checks", []) if c.get("check_id") != check_id]
            checks.append(self._check_dict(human))
            items = self._items_from_basis(current)
            outcome = flow.evaluate_verification(
                items, self._checks_from_dicts(checks),
                evidence_mode=current.get("evidence_mode", "production"),
                expected_candidate_digest=current.get("candidate_digest"),
                human_attested_check_ids=attested)
            new = {**current, "previous_ref": self._revision_ref(verification_ref, head).to_dict(),
                   "checks": checks, "human_attested_check_ids": sorted(attested),
                   "result": outcome.status, "passed": outcome.passed,
                   "complete": outcome.complete, "reasons": list(outcome.reasons),
                   "incomplete_reasons": list(outcome.incomplete_reasons),
                   "validity": "current",
                   "review": {"check_id": check_id, "result": result, "reason": reason,
                              "reviewer": ctx.scope.principal_id, "reviewed_at": _utc_now(),
                              "evidence_refs": evidence}}
            r = h.records.append_revision("verification", verification_ref.object_id, new,
                                          "verification.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            h.audit("verification.review_recorded",
                    payload={"verification_id": verification_ref.object_id, "check_id": check_id,
                             "result": result},
                    object_refs=[r.to_dict()])
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "verification.record_review").execute(cb)

    def check_validity(self, ctx: CommandContext, verification_ref: ObjectRef) -> CommandReceipt:
        """Re-compare the decisive basis and append a validity assessment.

        Changing the acceptance basis or the candidate makes the report stale and
        supersedes approvals that still reference it; unrelated edits do not.
        """
        def cb(h):
            self._require(CAP_VERIFICATION, ctx)
            current, head = self._head_payload(verification_ref.object_type,
                                              verification_ref.object_id)
            if current is None or head is None:
                raise KernelError(reference_not_found("verification report not found"))
            items = self._resolve_items([], current.get("acceptance_refs", []), current=True)
            reasons: list[str] = []
            if items and flow.acceptance_basis(items) != current.get("acceptance_basis"):
                reasons.append("acceptance basis changed")
            cand_ref = current.get("candidate_manifest_ref")
            if cand_ref:
                cand_payload, _ = self._head_payload(cand_ref["object_type"],
                                                     cand_ref["object_id"])
                if cand_payload is not None:
                    digest = cand_payload.get("candidate_digest") or cand_payload.get("digest")
                    if digest is not None and digest != current.get("candidate_digest"):
                        reasons.append("candidate changed")
            validity = "stale" if reasons else "current"
            if validity == current.get("validity"):
                h.audit("verification.validity_checked",
                        payload={"verification_id": verification_ref.object_id,
                                 "validity": validity})
                return
            new = {**current, "previous_ref": self._revision_ref(verification_ref, head).to_dict(),
                   "validity": validity, "validity_reasons": reasons,
                   "assessed_seq": h.records.commit_seq}
            r = h.records.append_revision("verification", verification_ref.object_id, new,
                                          "verification.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            if validity == "stale":
                self._supersede_approvals_for(h, ctx, verification_ref.object_id, reasons)
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "verification.run").execute(cb)

    def _supersede_approvals_for(self, h, ctx: CommandContext, verification_id: str,
                                 reasons: list[str]) -> None:
        for approval_id in self._approval_heads():
            payload, head = self._head_payload("approval", approval_id)
            if payload is None or head is None:
                continue
            if payload.get("status") not in (ApprovalStatus.PENDING.value,
                                             ApprovalStatus.APPROVED.value):
                continue
            if payload.get("apply_started"):
                continue
            snap = self._snapshot(payload.get("snapshot_id", ""))
            if snap is None:
                continue
            referenced = {r.get("object_id") for r in snap["body"].get("verification_refs", [])}
            if verification_id not in referenced:
                continue
            new = {**payload, "status": ApprovalStatus.SUPERSEDED.value,
                   "supersede_reason": "; ".join(reasons) or "decisive input changed",
                   "superseded_at": _utc_now()}
            r = h.records.append_revision("approval", approval_id, new, "approval.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            self._advance_task(h, ctx, snap["body"].get("task_ref"), "approval.superseded")

    # -------------------------------------------------- claim / apply / settle
    def claim_delivery(self, ctx: CommandContext, approval_id: str, snapshot_digest: str, *,
                       lease_seconds: int = 60) -> CommandReceipt:
        return self._claim(ctx, _new_id("operation"), approval_id, None, snapshot_digest,
                           lease_seconds=lease_seconds)

    def _claim_in_transaction(self,h,ctx,operation_id,approval_id,snapshot_id,snapshot_digest,*,lease_seconds):
        self._require(CAP_DELIVERY, ctx)
        approval, approval_head = self._head_payload("approval", approval_id)
        if approval is None or approval_head is None:
            raise KernelError(reference_not_found("approval not found"))
        if approval.get("status") != ApprovalStatus.APPROVED.value or _expired_at(approval.get("expires_at")):
            raise KernelError(approval_invalid(
                f"approval is {approval.get('status')}, not approved"))
        if approval.get("snapshot_digest") != snapshot_digest:
            raise KernelError(approval_invalid("snapshot digest mismatch"))
        if approval.get("operation_id"):
            raise KernelError(approval_invalid("approval is already bound to an operation"))
        snap = self._snapshot(approval["snapshot_id"])
        if snap is None:
            raise KernelError(reference_not_found("snapshot not found"))
        if not self._snapshot_eligible(snap):
            raise KernelError(_snapshot_changed(
                "decisive inputs changed; re-request approval"))
        problem = self._evidence_problem(snap["body"])
        if problem is not None:
            raise KernelError(problem)
        self._require_delivery_provider(snap, scope_mode=ctx.scope.mode)
        reserved = {"operation_id": operation_id, "approval_id": approval_id,
                    "snapshot_id": approval["snapshot_id"], "digest": snapshot_digest,
                    "task_id": (snap["body"].get("task_ref") or {}).get("object_id"),
                    "status": DeliveryState.CLAIMED.value, "epoch": 1,
                    "lease_until": _utc_in(lease_seconds), "provider": type(self.provider).__name__,
                    "apply_blocked": False, "claimed_seq": h.records.commit_seq}
        op_ref = h.records.append_revision("delivery", operation_id, reserved, "delivery.v1")
        h.records.publish_head(op_ref, "current")
        bound = {**approval, "operation_id": operation_id}
        approval_ref = h.records.append_revision("approval", approval_id, bound, "approval.v1")
        h.records.publish_head(approval_ref, "current",
                               expected_head_version=str(approval_head["head_version"]))
        h.audit("delivery.claimed", payload={"operation_id": operation_id,
                                             "approval_id": approval_id},
                object_refs=[op_ref.to_dict()])
        h.outcome.object_refs = (op_ref,)

    def _claim(self, ctx: CommandContext, operation_id: str, approval_id: str,
               snapshot_id: str | None, snapshot_digest: str,
               *, lease_seconds: int) -> CommandReceipt:
        def cb(h):
            self._claim_in_transaction(h,ctx,operation_id,approval_id,snapshot_id,snapshot_digest,lease_seconds=lease_seconds)
        return UnitOfWork(self.store, ctx, "delivery.claim").execute(cb)

    def apply_start_delivery(self, ctx: CommandContext, operation_id: str) -> CommandReceipt:
        return self._apply_start(ctx, operation_id)

    def _apply_start(self, ctx: CommandContext, operation_id: str) -> CommandReceipt:
        def cb(h):
            self._require(CAP_DELIVERY, ctx)
            payload, head = self._head_payload("delivery", operation_id)
            if payload is None or head is None:
                raise KernelError(reference_not_found("operation not found"))
            if payload.get("apply_blocked"):
                raise KernelError(BlockError("CANCEL_PENDING",
                                             "apply was blocked by a task termination",
                                             category="business"))
            if payload.get("status") != DeliveryState.CLAIMED.value:
                raise KernelError(invalid_input(
                    f"operation is {payload.get('status')}, cannot apply-start"))
            approval, approval_head = self._head_payload("approval", payload["approval_id"])
            if (approval is None or approval.get("status") != ApprovalStatus.APPROVED.value
                    or _expired_at(approval.get("expires_at"))
                    or approval.get("operation_id") != operation_id):
                raise KernelError(approval_invalid("approval is no longer valid at apply-start"))
            if _expired_at(payload.get("lease_until")):
                raise KernelError(approval_invalid("delivery claim expired before apply-start"))
            snap = self._snapshot(payload["snapshot_id"])
            if snap is None or snap["digest"] != payload["digest"] or not self._snapshot_eligible(snap):
                raise KernelError(_snapshot_changed("decisive inputs changed before apply-start"))
            problem = self._evidence_problem(snap["body"])
            if problem is not None:
                raise KernelError(problem)
            self._require_delivery_provider(snap, scope_mode=ctx.scope.mode)
            new = {**payload, "status": DeliveryState.APPLYING.value,
                   "apply_started_at": _utc_now(), "apply_started_seq": h.records.commit_seq}
            r = h.records.append_revision("delivery", operation_id, new, "delivery.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            self._record_delivery_blocker(h, r, new)
            approval, approval_head = self._head_payload("approval", payload["approval_id"])
            if approval is not None and approval_head is not None:
                aref = h.records.append_revision("approval", payload["approval_id"],
                                                 {**approval, "apply_started": True}, "approval.v1")
                h.records.publish_head(aref, "current",
                                       expected_head_version=str(approval_head["head_version"]))
            snap = self._snapshot(payload["snapshot_id"])
            if snap is not None:
                self._advance_task(h, ctx, snap["body"].get("task_ref"), "delivery.start")
            h.outcome.object_refs = (r,)
            h.outcome.operation_id = operation_id
        return UnitOfWork(self.store, ctx, "delivery.apply").execute(cb)

    def apply_delivery(self, ctx: CommandContext, approval_id: str, snapshot_id: str,
                       snapshot_digest: str) -> CommandReceipt:
        self._require(CAP_DELIVERY,ctx)
        replay = UnitOfWork(self.store, ctx, "delivery.apply")._check_idempotency()
        if replay is not None:
            return replay
        self.refresh_approvals(ctx)
        state={}
        def cb(h):
            payload,_=self._head_payload("approval",approval_id)
            if payload is None:
                raise KernelError(reference_not_found("approval not found"))
            if payload.get("status")!=ApprovalStatus.APPROVED.value:
                raise KernelError(approval_invalid("approval is not approved"))
            snap=self._snapshot(snapshot_id)
            if snap is None or snap["digest"]!=snapshot_digest:
                raise KernelError(_snapshot_changed("snapshot digest mismatch"))
            if payload.get("snapshot_id")!=snapshot_id or payload.get("snapshot_digest")!=snapshot_digest:
                raise KernelError(approval_invalid("approval belongs to another snapshot"))
            if not self._snapshot_eligible(snap):
                raise KernelError(_snapshot_changed("decisive inputs changed"))
            if self.provider is None:
                raise KernelError(capability_unavailable("no delivery provider registered"))
            operation_id="operation-"+sha256_digest({"principal":ctx.scope.principal_id,"apply":ctx.idempotency_key})[:20]
            self._claim_in_transaction(h,ctx,operation_id,approval_id,snapshot_id,snapshot_digest,lease_seconds=120)
            h.outcome.operation_id=operation_id
            state["snapshot"]=snap
        uow=UnitOfWork(self.store,ctx,"delivery.apply")
        receipt=uow.execute(cb)
        if receipt.status!="accepted" or not uow.did_commit:
            return receipt
        operation_id=receipt.operation_id
        started=self._apply_start(self._derive(ctx,f"start:{operation_id}",operation_id),operation_id)
        if started.status=="rejected":
            return receipt
        self._do_apply(ctx,operation_id,state["snapshot"])
        return receipt

    def _do_apply(self, ctx: CommandContext, operation_id: str, snap: dict[str, Any]) -> None:
        self._require(CAP_DELIVERY, ctx)
        started, _ = self._head_payload("delivery", operation_id)
        if started is None or started["status"] != DeliveryState.APPLYING.value:
            raise KernelError(invalid_input("delivery has not acquired apply-start"))
        started_epoch = started["epoch"]
        manifest = self._delivery_manifest(operation_id, snap)
        sink_id = manifest.required_sinks[0]
        sink_receipt = None
        provider_state = None
        error = None
        try:
            sink_receipt = self.provider.apply(manifest, sink_id, operation_id)
            provider_state = sink_receipt.get("state") if isinstance(sink_receipt, Mapping) else None
            error = sink_receipt.get("error") if isinstance(sink_receipt, Mapping) else None
        except Exception as exc:
            # A provider exception does not establish whether publication happened.
            error = exc.error.code if isinstance(exc, KernelError) else type(exc).__name__
            provider_state = "unknown"
        manifest_digest = manifest.digest()
        observation_diagnostics: dict[str, str] = {}
        effect = self._query_effect(operation_id, manifest_id=operation_id,
                                    expected_digest=manifest_digest,
                                    provider_state=provider_state,
                                    scope_mode=ctx.scope.mode,
                                    observation_diagnostics=observation_diagnostics)
        if error is None:
            error = observation_diagnostics.get("error")
        status = delivery_rules.delivery_state_for_effect(effect.status)

        settle_ctx = self._derive(ctx, f"settle:{operation_id}",
                                  {"operation_id": operation_id, "status": status})

        def cb(h):
            payload, head = self._head_payload("delivery", operation_id)
            if payload is None or head is None:
                raise KernelError(reference_not_found("operation not found"))
            if payload.get("epoch") != started_epoch or payload["status"] in _TERMINAL_DELIVERY:
                h.audit("delivery.late_settlement", {"operation_id": operation_id, "epoch": started_epoch})
                return
            new = {**payload, "status": status, "effect_status": effect.status,
                   "execution_terminal": effect.execution_terminal,
                   "manifest_digest": manifest_digest,
                   "sink_receipt": dict(sink_receipt) if isinstance(sink_receipt, Mapping) else None,
                   "error": error, "settled_seq": h.records.commit_seq}
            r = h.records.append_revision("delivery", operation_id, new, "delivery.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            self._record_delivery_blocker(h, r, new)
            h.outcome.object_refs = (r,)
        UnitOfWork(self.store, settle_ctx, "delivery.settle").execute(cb)

    # --------------------------------------------------------------- reconcile
    def delivery_reconcile(self, ctx: CommandContext, operation_id: str, *,
                           effect_receipt: Any | None = None, epoch: int | None = None,
                           external_fence: bool = False) -> CommandReceipt:
        self._require(CAP_DELIVERY, ctx)
        if effect_receipt is not None and ctx.scope.mode != "test":
            raise KernelError(permission_denied("supplied effect receipts are only available to explicit test scopes; configure a delivery provider"))
        payload, head = self._head_payload("delivery", operation_id)
        if payload is None:
            raise KernelError(reference_not_found("operation not found"))
        if payload.get("status") in _TERMINAL_DELIVERY:
            return self._noop(ctx, operation_id, payload, head)

        observation_diagnostics: dict[str, str] = {}
        effect = self._effect_for_reconcile(operation_id, payload, effect_receipt,
                                            external_fence=external_fence,
                                            scope_mode=ctx.scope.mode,
                                            observation_diagnostics=observation_diagnostics)
        if (effect.status == EffectStatus.ABSENT_FINAL.value
                and not delivery_rules.reconcile_requires_terminal_evidence(
                    effect.status, execution_terminal=effect.execution_terminal,
                    fence_evidence_ref=effect.fence_evidence_ref)):
            # "the target is missing right now" is not proof of no effect
            effect = EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)

        def cb(h):
            self._require(CAP_DELIVERY, ctx)
            current, cur_head = self._head_payload("delivery", operation_id)
            if current is None or cur_head is None:
                raise KernelError(reference_not_found("operation not found"))
            if epoch is not None and epoch != int(current.get("epoch", 1)):
                # a late result from an old epoch is audited, never applied
                stale_ref = ObjectRef(self.store.project_id, "delivery", operation_id,
                                      cur_head["revision_id"])
                h.audit("delivery.stale_epoch_result",
                        payload={"operation_id": operation_id, "result_epoch": epoch,
                                 "current_epoch": current.get("epoch")},
                        object_refs=[stale_ref.to_dict()])
                return
            state = current.get("status")
            if state in _TERMINAL_DELIVERY:
                h.audit("delivery.terminal_result_preserved", {"operation_id": operation_id})
                return
            new_state = self._reconciled_state(state, effect, current)
            if new_state == state:
                h.audit("delivery.reconcile_no_change",
                        payload={"operation_id": operation_id, "state": state,
                                 "effect": effect.status,
                                 **observation_diagnostics})
                return
            new = {**current, "status": new_state, "effect_status": effect.status,
                   "execution_terminal": effect.execution_terminal,
                   "reconciled": True, "reconciled_seq": h.records.commit_seq}
            if observation_diagnostics:
                new["error"] = observation_diagnostics["error"]
            if effect.verified_digest is not None:
                new["manifest_digest"] = effect.verified_digest
            if effect.fence_evidence_ref is not None:
                new["fence_evidence_ref"] = effect.fence_evidence_ref.to_dict()
            r = h.records.append_revision("delivery", operation_id, new, "delivery.v1")
            h.records.publish_head(r, "current", expected_head_version=str(cur_head["head_version"]))
            self._record_delivery_blocker(h, r, new)
            h.audit("delivery.reconciled", payload={"operation_id": operation_id, "from": state,
                                                    "to": new_state, "effect": effect.status,
                                                    **observation_diagnostics},
                    object_refs=[r.to_dict()])
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "delivery.reconcile").execute(cb)

    def _record_delivery_blocker(self, h, operation_ref: ObjectRef, payload: Mapping[str, Any]) -> None:
        blocker_id = "delivery-blocker-" + sha256_digest(
            {"operation_id": operation_ref.object_id})[:40]
        head = self.store.get_head("blocker", blocker_id, "current")
        if payload["status"] in _TERMINAL_DELIVERY:
            if head is not None:
                ref = ObjectRef(self.store.project_id, "blocker", blocker_id, head["revision_id"])
                body = self.store.get_revision(ref)["payload"]
                if body["status"] == "open":
                    resolved = h.blockers.resolve(ref, operation_ref,
                        expected_head_version=str(head["head_version"]))
                    h.audit("blocker.resolved", object_refs=[resolved.to_dict(), operation_ref.to_dict()])
            return
        if payload["status"] not in {"applying", "unknown"} or head is not None:
            return
        snapshot = self._snapshot(payload["snapshot_id"])
        task_ref = ObjectRef.from_dict(snapshot["body"]["task_ref"])
        ref = h.blockers.open(blocker_id, task_ref, "DELIVERY_OUTCOME_PENDING", operation_ref)
        h.audit("blocker.opened", object_refs=[ref.to_dict(), operation_ref.to_dict()])

    def _noop(self, ctx: CommandContext, operation_id: str, payload: dict[str, Any],
              head: Mapping[str, Any]) -> CommandReceipt:
        ref = ObjectRef(self.store.project_id, "delivery", operation_id, head["revision_id"])

        def cb(h):
            h.audit("delivery.reconcile_noop",
                    payload={"operation_id": operation_id, "status": payload.get("status")},
                    object_refs=[ref.to_dict()])
        return UnitOfWork(self.store, ctx, "delivery.reconcile").execute(cb)

    @staticmethod
    def _reconciled_state(state: str, effect: EffectReceipt, current: Mapping[str, Any]) -> str:
        target = delivery_rules.delivery_state_for_effect(effect.status)
        if state == DeliveryState.CLAIMED.value:
            if effect.status in (EffectStatus.APPLIED.value, EffectStatus.ABSENT_FINAL.value):
                return target
            # never started: an expired lease returns the claim to prepared
            if _expired_at(current.get("lease_until")):
                return DeliveryState.PREPARED.value
            return state
        if state == DeliveryState.PREPARED.value:
            return state
        return target

    # ------------------------------------------------------------- closure
    def task_close(self, ctx: CommandContext, task_ref: Any, applied_operation_ref: Any, *,
                   required_sinks: Iterable[str] = ("exports",),
                   source_flushed: bool = True) -> CommandReceipt:
        task = ObjectRef.from_dict(task_ref) if isinstance(task_ref, Mapping) else task_ref
        operation = (ObjectRef.from_dict(applied_operation_ref)
                     if isinstance(applied_operation_ref, Mapping) else applied_operation_ref)

        def cb(h):
            self._require(CAP_DELIVERY, ctx)
            self._exact_revision(task.to_dict(),kind="task")
            self._exact_revision(operation.to_dict(),kind="delivery")
            op, _ = self._head_payload("delivery", operation.object_id)
            if op is None:
                raise KernelError(reference_not_found("applied operation not found"))
            if op.get("status") != DeliveryState.APPLIED.value:
                raise KernelError(BlockError("APPROVAL_INVALID",
                                             f"operation is {op.get('status')}, not applied",
                                             category="business",
                                             recovery_action="settle the delivery first"))
            snap = self._snapshot(op["snapshot_id"])
            if snap is None:
                raise KernelError(reference_not_found("snapshot not found"))
            if not self._same_object(snap["body"]["task_ref"],task.to_dict()):
                raise KernelError(invalid_input("delivery belongs to another task"))
            problem = self._evidence_problem(snap["body"])
            if problem is not None:
                raise KernelError(problem)
            task_payload, task_head = self._head_payload("task", task.object_id)
            if task_payload is None or task_head is None:
                raise KernelError(reference_not_found("task not found"))
            transition = flow.task_transition(task_payload.get("phase"), "task.close")
            if isinstance(transition, flow.Rejection):
                raise KernelError(transition.error)

            body = snap["body"]
            artifacts = tuple(ArtifactRef(a["artifact_id"], a["sha256"], a["size_bytes"],
                                          a["media_type"], a["required"])
                              for a in body.get("artifacts", []))
            sinks = tuple(required_sinks)
            manifest = ArchiveManifest(manifest_id=f"archive-{operation.object_id}",
                                       snapshot_digest=snap["digest"],
                                       delivery_operation_refs=(operation.object_id,),
                                       artifacts=artifacts, required_sinks=sinks)
            manifest_ref = h.records.append_revision("archive_manifest", manifest.manifest_id,
                                                     manifest.body(), "archive_manifest.v1")
            h.records.publish_head(manifest_ref, "current")
            from ...data.queries.watermarks import ReadEnvelope
            watermarks = ReadEnvelope(self.store.conn, self.store.project_id, self.store.store_id).source_watermarks()
            sources_ready = source_flushed and watermarks["data_state"] in {"ok", "no_data"}
            overall = delivery_rules.archive_overall(sinks, {}, source_flushed=sources_ready)
            archive_ref = h.records.append_revision(
                "archive_status", task.object_id,
                {"task_id": task.object_id, "manifest_ref": manifest_ref.to_dict(),
                 "manifest_digest": manifest.digest(), "required_sinks": list(sinks),
                 "sink_states": {}, "source_flushed": sources_ready, "overall": overall,
                 "source_collection_requested": source_flushed,
                 "source_watermarks": watermarks, "source_check_seq": str(h.records.commit_seq),
                 "source_flush_basis": "local_observation_only",
                 "closed": True, "created_seq": h.records.commit_seq},
                "archive_status.v1")
            h.records.publish_head(archive_ref, "current")
            h.outbox.enqueue("archive", manifest.manifest_id, "archive.export",
                             payload_ref=json.dumps(manifest_ref.to_dict(), ensure_ascii=False))

            new_task = h.records.append_revision(
                "task", task.object_id,
                {**task_payload, "phase": transition.to_state, "terminal_outcome": "delivered",
                 "applied_operation_ref": operation.to_dict(),
                 "archive_manifest_ref": manifest_ref.to_dict(), "archive_overall": overall},
                "task.v1")
            h.records.publish_head(new_task, "current",
                                   expected_head_version=str(task_head["head_version"]))
            h.audit("task.closed", payload={"task_id": task.object_id,
                                            "operation_id": operation.object_id,
                                            "archive_overall": overall},
                    object_refs=[new_task.to_dict(), manifest_ref.to_dict()])
            h.outcome.object_refs = (new_task, manifest_ref, archive_ref)
        return UnitOfWork(self.store, ctx, "task.close").execute(cb)

    def task_terminate(self, ctx: CommandContext, task_ref: Any, outcome: str, reason: str,
                       unsettled_refs: Iterable[Any] = ()) -> CommandReceipt:
        task = ObjectRef.from_dict(task_ref) if isinstance(task_ref, Mapping) else task_ref

        def cb(h):
            self._require(CAP_DISPATCH, ctx)
            if outcome not in ("terminated", "cancelled"):
                raise KernelError(invalid_input(f"unknown outcome {outcome!r}"))
            if not reason:
                raise KernelError(invalid_input("task.terminate requires a reason"))
            task_payload, task_head = self._head_payload("task", task.object_id)
            if task_payload is None or task_head is None:
                raise KernelError(reference_not_found("task not found"))
            if flow.closed_is_terminal(task_payload.get("phase")):
                raise KernelError(invalid_input("task is already closed"))

            # active attempts must be settled; the caller's self-report is ignored
            active: list[str] = []
            for attempt_id in self._attempt_heads():
                ap, _ = self._head_payload("attempt", attempt_id)
                if not ap:
                    continue
                ref = ap.get("task_ref") or {}
                if not isinstance(ref, Mapping) or ref.get("object_id") != task.object_id:
                    continue
                if not flow.attempt_is_terminal(ap.get("status", "unknown")):
                    active.append(attempt_id)
            if active:
                raise KernelError(required_fact_unknown(
                    f"active attempts not settled: {sorted(active)}"))

            # the service queries the real delivery state itself
            blocked: list[str] = []
            settled: list[dict[str, Any]] = []
            unclaimed: list[str] = []
            for operation_id in self._delivery_heads():
                op, op_head = self._head_payload("delivery", operation_id)
                if not op or op.get("task_id") != task.object_id:
                    continue
                state = op.get("status")
                if state == DeliveryState.CLAIMED.value:
                    unclaimed.append(operation_id)
                    r = h.records.append_revision(
                        "delivery", operation_id,
                        {**op, "status": DeliveryState.PREPARED.value, "apply_blocked": True,
                         "unclaim_reason": "task.terminate"}, "delivery.v1")
                    h.records.publish_head(r, "current",
                                           expected_head_version=str(op_head["head_version"]))
                    settled.append({"operation_id": operation_id, "status": "prepared"})
                elif state in (DeliveryState.APPLYING.value, DeliveryState.UNKNOWN.value):
                    blocked.append(operation_id)
                else:
                    settled.append({"operation_id": operation_id, "status": state})
            if blocked:
                raise KernelError(BlockError(
                    "EXTERNAL_OUTCOME_UNKNOWN",
                    f"delivery still in flight: {sorted(blocked)}",
                    retryable=True, category="infrastructure",
                    recovery_action="delivery.reconcile"))

            transition = flow.task_transition(task_payload.get("phase"), "task.terminate")
            if isinstance(transition, flow.Rejection):
                raise KernelError(transition.error)
            new_task = h.records.append_revision(
                "task", task.object_id,
                {**task_payload, "phase": transition.to_state, "terminal_outcome": outcome,
                 "terminate_reason": reason,
                 "unsettled_refs": [self._ref_dict(r) for r in unsettled_refs],
                 "settled_deliveries": settled, "unclaimed_operations": unclaimed},
                "task.v1")
            h.records.publish_head(new_task, "current",
                                   expected_head_version=str(task_head["head_version"]))
            h.audit("task.terminated", payload={"task_id": task.object_id, "outcome": outcome,
                                                "reason": reason},
                    object_refs=[new_task.to_dict()])
            h.outcome.object_refs = (new_task,)
        return UnitOfWork(self.store, ctx, "task.terminate").execute(cb)

    def record_sink_result(self, ctx: CommandContext, task_id: str, sink_id: str, state: str, *,
                           digest: str = "", locator: str | None = None,
                           source_flushed: bool | None = None, verified: bool = False) -> CommandReceipt:
        """Callback for a real archive sink (P05); recomputes archive completeness."""
        def cb(h):
            self._require(CAP_DELIVERY, ctx)
            status, head = self._head_payload("archive_status", task_id)
            if status is None or head is None:
                raise KernelError(reference_not_found("no archive status for task"))
            if sink_id not in status.get("required_sinks", []):
                raise KernelError(invalid_input(f"sink {sink_id!r} is not required"))
            if state not in tuple(s.value for s in ArchiveSinkState):
                raise KernelError(invalid_input(f"unknown sink state {state!r}"))
            manifest = self._exact_revision(status["manifest_ref"], kind="archive_manifest")
            if state == "succeeded" and (digest != manifest["digest"] or verified is not True):
                raise KernelError(artifact_digest_mismatch("archive success requires the pinned manifest digest and verified receipt"))
            sink_states = {**status.get("sink_states", {}), sink_id: state}
            requested = status.get("source_collection_requested", status.get("source_flushed", False)) if source_flushed is None \
                else source_flushed
            from ...data.queries.watermarks import ReadEnvelope
            watermarks = ReadEnvelope(self.store.conn, self.store.project_id, self.store.store_id).source_watermarks()
            flushed = requested and watermarks["data_state"] in {"ok", "no_data"}
            overall = delivery_rules.archive_overall(status["required_sinks"], sink_states,
                                                     source_flushed=flushed)
            new = {**status, "source_watermarks": watermarks, "source_collection_requested": requested,
                   "source_check_seq": str(h.records.commit_seq),
                   "source_flush_basis": "local_observation_only", "sink_states": sink_states, "source_flushed": flushed,
                   "overall": overall,
                   "receipts": {**status.get("receipts", {}),
                                sink_id: {"state": state, "digest": digest, "locator": locator, "verified": verified is True,
                                          "recorded_seq": h.records.commit_seq}},
                   "updated_seq": h.records.commit_seq}
            r = h.records.append_revision("archive_status", task_id, new, "archive_status.v1")
            h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))
            h.outcome.object_refs = (r,)
        return UnitOfWork(self.store, ctx, "archive.export").execute(cb)

    # ------------------------------------------------------------- helpers
    def _effect_for_reconcile(self, operation_id: str, payload: Mapping[str, Any],
                              effect_receipt: Any | None, *,
                              external_fence: bool,
                              scope_mode: str,
                              observation_diagnostics: dict[str, str] | None = None
                              ) -> EffectReceipt:
        """Use a supplied receipt, otherwise ask the real provider/target.

        Without a provider there is nothing to query, and the result must stay
        unknown rather than being invented.
        """
        if effect_receipt is not None:
            return self._normalise_effect(operation_id, effect_receipt,
                                          external_fence=external_fence,
                                          expected_digest=self._expected_manifest_digest(payload))
        if self.provider is None:
            return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
        return self._query_effect(operation_id, manifest_id=operation_id,
                                  expected_digest=self._expected_manifest_digest(payload),
                                  provider_state=None,
                                  scope_mode=scope_mode,
                                  observation_diagnostics=observation_diagnostics)

    def _expected_manifest_digest(self, payload: Mapping[str, Any]) -> str | None:
        """The digest the delivery should have produced, from the frozen snapshot."""
        snap = self._snapshot(payload.get("snapshot_id", ""))
        if snap is None:
            return None
        digest = self._delivery_manifest(payload["operation_id"], snap).digest()
        if payload.get("manifest_digest") not in (None, digest):
            raise KernelError(artifact_digest_mismatch("delivery manifest digest differs from the frozen snapshot"))
        return digest

    def _query_effect(self, operation_id: str, *, manifest_id: str,
                      expected_digest: str | None, provider_state: str | None,
                      scope_mode: str,
                      observation_diagnostics: dict[str, str] | None = None
                      ) -> EffectReceipt:
        """Read validated evidence; unavailable or invalid observations stay unknown."""
        payload, _ = self._head_payload("delivery", operation_id)
        snapshot = self._snapshot(payload["snapshot_id"]) if payload else None
        manifest = (self._delivery_manifest(operation_id, snapshot)
                    if snapshot is not None else None)
        if self.provider is None:
            return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
        try:
            if snapshot is not None:
                self._require_delivery_provider(snapshot, scope_mode=scope_mode)
            observed = self.provider.observe(operation_id, manifest_id, expected_digest,
                                             provider_state=provider_state, manifest=manifest)
            return self._normalise_effect(operation_id, observed, external_fence=False,
                                          expected_digest=expected_digest)
        except Exception as exc:
            if observation_diagnostics is not None:
                observation_diagnostics["error"] = type(exc).__name__
            return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)

    def _normalise_effect(self, operation_id: str, receipt: Any, *, external_fence: bool,
                          expected_digest: str | None = None) -> EffectReceipt:
        if receipt is None:
            return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
        if isinstance(receipt, Mapping):
            if receipt.get("operation_id") != operation_id:
                raise KernelError(invalid_input("effect receipt operation_id differs or is missing"))
            try:
                fence_ref = (ObjectRef.from_dict(receipt["fence_evidence_ref"])
                             if receipt.get("fence_evidence_ref") else None)
            except (KeyError, TypeError, ValueError) as exc:
                raise KernelError(invalid_input("fence evidence must be an exact object reference")) from exc
            if fence_ref is not None:
                self._validate_fence(fence_ref, operation_id)
            status = receipt.get("status", EffectStatus.UNKNOWN.value)
            if status not in {item.value for item in EffectStatus}:
                raise KernelError(invalid_input("effect receipt has an invalid status"))
            if "execution_terminal" in receipt and type(receipt["execution_terminal"]) is not bool:
                return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
            if status == EffectStatus.APPLIED.value and (expected_digest is None or receipt.get("verified_digest") != expected_digest):
                return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
            if (status == EffectStatus.ABSENT_FINAL.value
                    and receipt.get("execution_terminal") is not True and fence_ref is None):
                return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
            return EffectReceipt(
                operation_id, receipt.get("status", EffectStatus.UNKNOWN.value),
                execution_terminal=receipt.get("execution_terminal") is True,
                fence_evidence_ref=fence_ref,
                verified_digest=receipt.get("verified_digest"))
        if isinstance(receipt, EffectReceipt):
            if receipt.operation_id != operation_id:
                raise KernelError(invalid_input("effect receipt operation_id differs"))
            if receipt.status not in {item.value for item in EffectStatus}:
                raise KernelError(invalid_input("effect receipt has an invalid status"))
            if receipt.fence_evidence_ref is not None:
                self._validate_fence(receipt.fence_evidence_ref, operation_id)
            if receipt.status == EffectStatus.APPLIED.value and (expected_digest is None or receipt.verified_digest != expected_digest):
                return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
            if type(receipt.execution_terminal) is not bool:
                return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
            if (receipt.status == EffectStatus.ABSENT_FINAL.value
                    and not receipt.execution_terminal and receipt.fence_evidence_ref is None):
                return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)
            return receipt
        return EffectReceipt(operation_id, EffectStatus.UNKNOWN.value)

    def _validate_fence(self, fence_ref: ObjectRef, operation_id: str) -> None:
        row = self._exact_revision(fence_ref.to_dict(), kind="fence")
        if row["payload"].get("operation_id") != operation_id:
            raise KernelError(invalid_input("fence evidence belongs to a different operation"))

    def _resolve_items(self, provided: list[Any], acceptance_refs: list[Any], *,
                       current: bool = False) -> list[AcceptanceItem]:
        items: list[AcceptanceItem] = []
        for raw in provided:
            items.append(raw if isinstance(raw, AcceptanceItem) else self._item_from_dict(raw))
        for raw in acceptance_refs:
            ref = raw if isinstance(raw, ObjectRef) else ObjectRef.from_dict(raw)
            rev = None
            if current:
                head = self.store.get_head(ref.object_type, ref.object_id, "current")
                if head is not None:
                    rev = self.store.get_revision(
                        ObjectRef(self.store.project_id, ref.object_type, ref.object_id,
                                  head["revision_id"]))
            if rev is None:
                rev = self.store.get_revision(ref)
            if rev is None:
                raise KernelError(reference_not_found(
                    f"acceptance {ref.object_id}@{ref.revision_id} not found"))
            payload = rev["payload"]
            if isinstance(payload, list):
                declared = payload
            elif isinstance(payload, Mapping) and "acceptance_items" in payload:
                declared = payload["acceptance_items"]
            elif isinstance(payload, Mapping) and "item_id" in payload:
                declared = [payload]
            else:
                raise KernelError(required_fact_unknown(
                    f"acceptance {ref.object_id} declares no acceptance items"))
            for entry in declared:
                items.append(self._item_from_dict(entry))
        return items

    def _items_from_basis(self, report: Mapping[str, Any]) -> list[AcceptanceItem]:
        return [self._item_from_dict(i) for i in report.get("acceptance_basis", {}).get("items", [])]

    @staticmethod
    def _item_from_dict(raw: Mapping[str, Any]) -> AcceptanceItem:
        return AcceptanceItem(
            item_id=raw["item_id"],
            requirement_ref=ObjectRef.from_dict(raw["requirement_ref"]),
            recipe_ref=ObjectRef.from_dict(raw["recipe_ref"]),
            required=raw.get("required", True),
            evidence_type=raw.get("evidence_type", "automated_test"),
            criterion=raw.get("criterion", ""))

    def _resolve_checks(self, provided: list[Any], items: list[AcceptanceItem],
                        check_provider: Callable[[list[AcceptanceItem]], list[Any]] | None
                        ) -> list[CheckResult]:
        checks: list[CheckResult] = []
        for raw in provided:
            checks.append(raw if isinstance(raw, CheckResult) else self._check_from_dict(raw))
        if check_provider is not None:
            for raw in check_provider(items) or ():
                checks.append(raw if isinstance(raw, CheckResult) else self._check_from_dict(raw))
        return checks

    @staticmethod
    def _check_from_dict(raw: Mapping[str, Any]) -> CheckResult:
        return CheckResult(
            check_id=raw["check_id"],
            recipe_ref=ObjectRef.from_dict(raw["recipe_ref"]),
            subject_ref=ObjectRef.from_dict(raw["subject_ref"]) if raw.get("subject_ref") else None,
            candidate_digest=raw.get("candidate_digest"),
            result=raw.get("result", "unknown"),
            evidence_refs=tuple(ObjectRef.from_dict(r) for r in raw.get("evidence_refs", [])),
            evidence_mode=raw.get("evidence_mode", "test"))

    @staticmethod
    def _check_dict(check: CheckResult) -> dict[str, Any]:
        return check.to_dict()

    @staticmethod
    def _checks_from_dicts(raws: Iterable[Mapping[str, Any]]) -> list[CheckResult]:
        return [DeliveryService._check_from_dict(r) for r in raws]

    @staticmethod
    def _find_item(report: Mapping[str, Any], check_id: str) -> dict[str, Any] | None:
        for item in report.get("acceptance_basis", {}).get("items", []):
            if item.get("item_id") == check_id:
                return item
        return None

    def _revision_ref(self, ref: ObjectRef, head: Mapping[str, Any] | None) -> ObjectRef:
        revision_id = head["revision_id"] if head is not None else ref.revision_id
        return ObjectRef(ref.project_id, ref.object_type, ref.object_id, revision_id)

    @staticmethod
    def _ref_dict(ref: Any) -> dict[str, Any]:
        if isinstance(ref, ObjectRef):
            return ref.to_dict()
        if isinstance(ref, Mapping):
            return dict(ref)
        return ref.to_dict()
