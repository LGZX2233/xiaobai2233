"""KnowledgeService: versioned sources, budget-aware context and real feedback.

Persistence goes through the P01 generic revision ledger via UnitOfWork and
Records; this module never executes DDL and never opens a second SQL writer.
Object types used by this module (all within `project.sqlite`, scoped to
`store.project_id`):

  knowledge               KnowledgeRevision, versioned (ordinal / current head)
  knowledge_use           one immutable use event per source_use_key (dedup)
  knowledge_outcome       one immutable outcome per source_outcome_key (dedup)
  promotion_task          explicit project -> shared promotion decisions
  knowledge_checkpoint    FeedbackConsumer resume cursors

Reads are typed SELECTs over the store connection restricted to these types
(see docs/handoffs/P08.md ChangeRequest for a first-class P01/P06 read API).
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable, Optional

from ..contracts import sha256_digest
from ..contracts.dto import CommandContext, ObjectRef, ResolvedScope
from ..contracts.errors import (
    KernelError,
    invalid_input,
    permission_denied,
    reference_not_found,
    scope_mismatch,
)
from ..data.store.store import Store
from ..data.store.uow import UnitOfWork
from .models import (
    ContextManifest,
    ContextRequest,
    FeedbackReceipt,
    KnowledgeRevision,
    OutcomeEvent,
    PromotionTask,
    ScoreRecord,
    SourceMaterial,
    UseEvent,
)
from .resolver import ContextResolver
from .scoring import ScoreEngine, ScoringConfig
from .token_meter import DeterministicTokenMeter, TokenMeterPort

_KNOWLEDGE_TYPE = "knowledge"
_USE_TYPE = "knowledge_use"
_OUTCOME_TYPE = "knowledge_outcome"
_PROMOTION_TYPE = "promotion_task"
_CHECKPOINT_TYPE = "knowledge_checkpoint"

_USE_SCHEMA = "knowledge_use.v1"
_OUTCOME_SCHEMA = "knowledge_outcome.v1"
_KNOWLEDGE_SCHEMA = "knowledge.v1"
_PROMOTION_SCHEMA = "promotion_task.v1"
_CHECKPOINT_SCHEMA = "knowledge_checkpoint.v1"


def _dedup_object_id(prefix: str, key: str) -> str:
    """Stable object_id for a dedup key; full key is preserved in the payload."""
    return f"{prefix}-{sha256_digest({'key': key})[:32]}"


def _command_key(kind: str, object_id: str) -> str:
    return f"{kind}-{sha256_digest({'object_id': object_id})[:24]}"


class KnowledgeService:
    def __init__(self, store: Store, meter: TokenMeterPort | None = None,
                 score_config: ScoringConfig | None = None):
        self.store = store
        self.meter = meter or DeterministicTokenMeter()
        self.resolver = ContextResolver(self.meter)
        self.score_config = score_config or ScoringConfig.exponential()
        self.engine = ScoreEngine(self.score_config)

    # -- permission / scope -------------------------------------------------
    def _guard(self, scope: ResolvedScope) -> None:
        if scope.project_id != self.store.project_id:
            raise KernelError(scope_mismatch(
                f"scope project {scope.project_id} does not match store "
                f"project {self.store.project_id}"))

    def _require_capability(self, scope: ResolvedScope, capability: str) -> None:
        self._guard(scope)
        if capability not in scope.capabilities:
            raise KernelError(permission_denied(
                f"capability {capability!r} is required"))

    # -- context ------------------------------------------------------------
    def resolve_context(self, request: ContextRequest,
                        materials: Iterable[SourceMaterial]) -> ContextManifest:
        """Pure resolve; every selected exact revision is then verified."""
        manifest = self.resolver.resolve(request, materials)
        self.verify_manifest(manifest)
        return manifest

    def verify_manifest(self, manifest: ContextManifest) -> None:
        """Every selected source_ref must exist with the recorded digest.

        AC33 + task acceptance #2: invalid revision or digest mismatch blocks.
        """
        for s in manifest.selections:
            row = self.store.get_revision(s.source_ref)
            if row is None:
                raise KernelError(reference_not_found(
                    f"selected source {s.source_ref.object_type}/"
                    f"{s.source_ref.object_id}@{s.source_ref.revision_id} not found"))
            if s.content_digest and row["digest"] != s.content_digest:
                from ..contracts.errors import artifact_digest_mismatch
                raise KernelError(artifact_digest_mismatch(
                    f"source {s.key} digest does not match stored revision"))

    # -- knowledge revisions --------------------------------------------------
    def record_knowledge(self, scope: ResolvedScope, revision: KnowledgeRevision,
                         knowledge_id: str | None = None,
                         idempotency_key: str | None = None) -> ObjectRef:
        self._guard(scope)
        object_id = knowledge_id or ("k-" + uuid.uuid4().hex)
        key = idempotency_key or _command_key("knowledge", object_id)
        result: dict[str, Any] = {}

        def _tx(h: Any) -> None:
            head = self.store.get_head(_KNOWLEDGE_TYPE, object_id, "current")
            if head is not None:
                result["ref"] = self._ref(object_id, head["revision_id"])
                result["duplicate"] = True
                return
            ref = h.records.append_revision(_KNOWLEDGE_TYPE, object_id,
                                            revision.to_dict(), _KNOWLEDGE_SCHEMA)
            h.records.publish_head(ref, "current", None)
            h.audit("knowledge.recorded", revision.to_dict(), "knowledge.v1",
                    [ref.to_dict()])
            result["ref"] = ref
            result["duplicate"] = False

        self._execute(scope, key, {"command": "knowledge.record_use", "object_id": object_id,
                                   "payload": revision.to_dict()}, _tx)
        if not result:
            head = self.store.get_head(_KNOWLEDGE_TYPE, object_id, "current")
            if head is not None:
                return self._ref(object_id, head["revision_id"])
        return result["ref"]

    def revise_knowledge(self, scope: ResolvedScope, knowledge_ref: ObjectRef,
                         revision: KnowledgeRevision) -> ObjectRef:
        """Append a new revision and CAS-publish the current head."""
        self._guard(scope)
        head = self.store.get_head(_KNOWLEDGE_TYPE, knowledge_ref.object_id, "current")
        if head is None:
            raise KernelError(reference_not_found(
                f"knowledge {knowledge_ref.object_id} does not exist"))
        expected = str(head["head_version"])
        result: dict[str, Any] = {}

        def _tx(h: Any) -> None:
            ref = h.records.append_revision(_KNOWLEDGE_TYPE, knowledge_ref.object_id,
                                            revision.to_dict(), _KNOWLEDGE_SCHEMA,
                                            parent_ref=knowledge_ref)
            h.records.publish_head(ref, "current", expected)
            h.audit("knowledge.revised", revision.to_dict(), "knowledge.v1",
                    [ref.to_dict()])
            result["ref"] = ref

        self._execute(scope, _command_key("revise", knowledge_ref.object_id),
                      {"command": "knowledge.revise", "knowledge_ref": knowledge_ref.to_dict(),
                       "payload": revision.to_dict()}, _tx)
        if not result:
            head = self.store.get_head(_KNOWLEDGE_TYPE, knowledge_ref.object_id, "current")
            if head is not None:
                return self._ref(knowledge_ref.object_id, head["revision_id"])
        return result["ref"]

    def read_knowledge(self, object_id: str) -> dict[str, Any] | None:
        head = self.store.get_head(_KNOWLEDGE_TYPE, object_id, "current")
        if head is None:
            return None
        return self.store.get_revision(self._ref(object_id, head["revision_id"]))

    # -- use / outcome feedback ----------------------------------------------
    def record_use(self, scope: ResolvedScope, knowledge_ref: ObjectRef,
                   source_use_key: str, use_kind: str,
                   context_ref: ObjectRef | None = None) -> FeedbackReceipt:
        self._guard(scope)
        if self.store.get_revision(knowledge_ref) is None:
            raise KernelError(reference_not_found(
                f"knowledge ref {knowledge_ref.object_id}@{knowledge_ref.revision_id} "
                f"not found"))
        event = UseEvent(source_use_key=source_use_key, use_kind=use_kind,
                         knowledge_ref=knowledge_ref,
                         project_id=scope.project_id, context_ref=context_ref)
        dup = self._append_unique(scope, _USE_TYPE,
                                  _dedup_object_id("use", source_use_key),
                                  event.to_dict(), _USE_SCHEMA,
                                  {"command": "knowledge.record_use",
                                   "source_use_key": source_use_key},
                                  "knowledge.use")
        return self._feedback(source_use_key, dup)

    def record_outcome(self, scope: ResolvedScope, source_outcome_key: str,
                       outcome_kind: str, use_source_key: str = "",
                       verified_result_ref: ObjectRef | None = None) -> FeedbackReceipt:
        self._guard(scope)
        event = OutcomeEvent(source_outcome_key=source_outcome_key,
                             outcome_kind=outcome_kind,
                             project_id=scope.project_id,
                             use_source_key=use_source_key,
                             verified_result_ref=verified_result_ref)
        dup = self._append_unique(scope, _OUTCOME_TYPE,
                                  _dedup_object_id("outcome", source_outcome_key),
                                  event.to_dict(), _OUTCOME_SCHEMA,
                                  {"command": "knowledge.record_outcome",
                                   "source_outcome_key": source_outcome_key},
                                  "knowledge.outcome")
        return self._feedback(source_outcome_key, dup)

    # -- promotion -----------------------------------------------------------
    def promote(self, scope: ResolvedScope, knowledge_ref: ObjectRef,
                reviewed_scope: str, human_decision_ref: ObjectRef,
                shared_sink: Any = None) -> PromotionTask:
        """Explicit human-reviewed promotion to the shared scope.

        Requires `knowledge.share`. The source project record is never deleted;
        the shared copy is verified by digest before the promotion is marked
        completed (design 05 §1). `shared_sink` writes into the shared store and
        returns a dict {"store_id","object_id","revision_id","digest"}.
        """
        self._require_capability(scope, "knowledge.share")
        row = self.store.get_revision(knowledge_ref)
        if row is None:
            raise KernelError(reference_not_found(
                f"knowledge {knowledge_ref.object_id}@{knowledge_ref.revision_id} not found"))

        object_id = "promo-" + sha256_digest(
            {"knowledge_ref": knowledge_ref.to_dict(),
             "human_decision_ref": human_decision_ref.to_dict()})[:24]

        task = PromotionTask(knowledge_ref=knowledge_ref,
                             reviewed_scope=reviewed_scope,
                             human_decision_ref=human_decision_ref,
                             state="pending")
        if shared_sink is not None:
            shared_ref = shared_sink.write(row["digest"], row["payload"])
            if shared_ref.get("digest") != row["digest"]:
                task = PromotionTask(knowledge_ref=knowledge_ref,
                                     reviewed_scope=reviewed_scope,
                                     human_decision_ref=human_decision_ref,
                                     state="failed",
                                     shared_ref=shared_ref)
            else:
                task = PromotionTask(knowledge_ref=knowledge_ref,
                                     reviewed_scope=reviewed_scope,
                                     human_decision_ref=human_decision_ref,
                                     state="completed",
                                     target_store_id=shared_ref.get("store_id", ""),
                                     shared_ref=shared_ref)

        result: dict[str, Any] = {}

        def _tx(h: Any) -> None:
            ref = h.records.append_revision(_PROMOTION_TYPE, object_id,
                                            task.to_dict(), _PROMOTION_SCHEMA)
            h.records.publish_head(ref, "current", None)
            h.audit("knowledge.promotion", task.to_dict(), "promotion_task.v1",
                    [ref.to_dict()])
            result["ref"] = ref

        self._execute(scope, _command_key("promote", object_id),
                      {"command": "knowledge.promote", "payload": task.to_dict()}, _tx)
        return task

    # -- scoring -------------------------------------------------------------
    def score(self) -> ScoreRecord:
        uses = [UseEvent.from_dict(e["payload"]) for e in self._list_events(_USE_TYPE)]
        outcomes = [OutcomeEvent.from_dict(e["payload"])
                    for e in self._list_events(_OUTCOME_TYPE)]
        return self.engine.score(uses, outcomes)

    # -- internals -----------------------------------------------------------
    def _ref(self, object_id: str, revision_id: str) -> ObjectRef:
        return ObjectRef(self.store.project_id, _KNOWLEDGE_TYPE, object_id, revision_id)

    def _execute(self, scope: ResolvedScope, key: str, input_payload: dict[str, Any],
                 callback: Any) -> None:
        ctx = CommandContext(scope=scope, command_id="cmd-" + uuid.uuid4().hex,
                             idempotency_key=key,
                             input_hash=sha256_digest(input_payload))
        UnitOfWork(self.store, ctx, input_payload.get("command", "knowledge.command")) \
            .execute(callback)

    def _append_unique(self, scope: ResolvedScope, obj_type: str, object_id: str,
                       payload: dict[str, Any], schema: str,
                       input_payload: dict[str, Any], audit_type: str) -> bool:
        """Append one immutable event; returns True when it was a duplicate."""
        if self.store.get_head(obj_type, object_id, "current") is not None:
            return True
        result: dict[str, Any] = {"duplicate": False}

        def _tx(h: Any) -> None:
            head = self.store.get_head(obj_type, object_id, "current")
            if head is not None:
                result["duplicate"] = True
                result["ref"] = ObjectRef(self.store.project_id, obj_type, object_id,
                                          head["revision_id"])
                return
            ref = h.records.append_revision(obj_type, object_id, payload, schema)
            h.records.publish_head(ref, "current", None)
            h.audit(audit_type, payload, "knowledge.v1", [ref.to_dict()])
            result["ref"] = ref

        self._execute(scope, _command_key(obj_type, object_id), input_payload, _tx)
        if not result:
            # command-level idempotent replay: callback did not run again
            return self.store.get_head(obj_type, object_id, "current") is not None
        return result["duplicate"]

    def _feedback(self, event_key: str, duplicate: bool) -> FeedbackReceipt:
        score = self.score()
        return FeedbackReceipt(event_key=event_key,
                               score_version=self.score_config.score_version,
                               new_score=score.score,
                               causal_refs=score.causal_refs,
                               duplicate=duplicate)

    def _list_events(self, obj_type: str) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            "SELECT object_id, revision_id, payload_json, commit_seq, ordinal"
            " FROM revision WHERE project_id=? AND type=?"
            " ORDER BY commit_seq, ordinal",
            (self.store.project_id, obj_type)).fetchall()
        return [{"object_id": r[0], "revision_id": r[1],
                 "payload": json.loads(r[2]), "commit_seq": r[3], "ordinal": r[4]}
                for r in rows]


class FeedbackConsumer:
    """Optional consumer of knowledge feedback events.

    Disabling never deletes records (they are immutable revisions); re-enabling
    replays idempotently - the score is always rebuilt from the full append-only
    ledger, so duplicate event keys never double-count and a restarted consumer
    reproduces the same score (AC34 / task acceptance #4).
    """

    def __init__(self, service: KnowledgeService, name: str):
        self.service = service
        self.name = name
        self.disabled = False
        self.seen_keys: set[str] = set()
        self._uses: list[UseEvent] = []
        self._outcomes: list[OutcomeEvent] = []
        self.score_record: ScoreRecord | None = None

    # -- lifecycle -----------------------------------------------------------
    def disable(self) -> None:
        self.disabled = True
        self._save_checkpoint()

    def enable(self) -> None:
        self.disabled = False

    def consume(self) -> list[dict[str, Any]]:
        if self.disabled:
            return []
        applied: list[dict[str, Any]] = []
        self._uses = []
        self._outcomes = []
        max_seq = 0
        for ev in self.service._list_events(_USE_TYPE):
            key = ev["payload"]["source_use_key"]
            max_seq = max(max_seq, ev["commit_seq"])
            if key not in self.seen_keys:
                self.seen_keys.add(key)
                applied.append({"type": "use", "key": key, "seq": ev["commit_seq"]})
            self._uses.append(UseEvent.from_dict(ev["payload"]))
        for ev in self.service._list_events(_OUTCOME_TYPE):
            key = ev["payload"]["source_outcome_key"]
            max_seq = max(max_seq, ev["commit_seq"])
            if key not in self.seen_keys:
                self.seen_keys.add(key)
                applied.append({"type": "outcome", "key": key, "seq": ev["commit_seq"]})
            self._outcomes.append(OutcomeEvent.from_dict(ev["payload"]))
        self.score_record = self.service.engine.score(self._uses, self._outcomes)
        if applied:
            self._save_checkpoint(max_seq)
        return applied

    # -- checkpoint (typed, append-only; never deletes) ------------------------
    def _checkpoint_id(self) -> str:
        return f"ckpt-{sha256_digest({'consumer': self.name})[:32]}"

    def _save_checkpoint(self, last_seq: int = 0) -> None:
        payload = {"consumer": self.name, "last_commit_seq": last_seq,
                   "disabled": self.disabled, "event_count": len(self.seen_keys)}
        object_id = self._checkpoint_id()
        head = self.service.store.get_head(_CHECKPOINT_TYPE, object_id, "current")
        expected = None if head is None else str(head["head_version"])
        key = _command_key(_CHECKPOINT_TYPE,
                           f"{object_id}-{sha256_digest(payload)[:24]}")

        def _tx(h: Any) -> None:
            ref = h.records.append_revision(_CHECKPOINT_TYPE, object_id, payload,
                                            _CHECKPOINT_SCHEMA)
            h.records.publish_head(ref, "current", expected)

        self.service._execute(
            self._scope(), key,
            {"command": "knowledge.checkpoint", "consumer": self.name, "payload": payload},
            _tx)

    def _scope(self) -> ResolvedScope:
        return ResolvedScope(project_id=self.service.store.project_id,
                             store_id=self.service.store.store_id,
                             principal_id="system.ingest",
                             capabilities=frozenset({"system.ingest"}), mode="test")
