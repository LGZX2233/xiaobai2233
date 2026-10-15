"""Typed P08 knowledge DTOs.

Pure frozen dataclasses; no sqlite3/Path/subprocess/DSH imports. Identifiers,
revision ids and digests are validated on construction so no arbitrary dict can
reach the service layer. JCS/SHA-256 digests are computed with the frozen
contract helper (D13).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ..contracts import sha256_digest
from ..contracts.dto import ObjectRef

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")

USE_KINDS = ("retrieved", "injected", "adopted")
OUTCOME_KINDS = ("success", "failure", "rollback", "correction")
VALIDITY_VALUES = ("current", "stale")
FRESHNESS_VALUES = ("fresh", "stale", "expired")
TOKEN_MODES = ("exact", "estimated")
KNOWLEDGE_STATUSES = ("candidate", "reviewed", "validated", "deprecated")
KNOWLEDGE_SCOPES = ("project", "shared")


def _require_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"{name} must match {_ID_RE.pattern!r}, got {value!r}")
    return value


def _require_digest(value: str, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.match(value):
        raise ValueError(f"{name} must be a 64-char lowercase sha256 hex, got {value!r}")
    return value


def _object_refs_to_dicts(refs: tuple[ObjectRef, ...]) -> list[dict[str, str]]:
    return [r.to_dict() for r in refs]


# --- context resolution ------------------------------------------------------

@dataclass(frozen=True)
class SourceMaterial:
    """One candidate context material. `source_ref` is an exact project revision."""

    key: str
    project_id: str
    source_ref: ObjectRef
    source_kind: str
    validity: str = "current"
    freshness: str = "fresh"
    token_count: Optional[int] = None
    token_mode: str = "exact"
    priority: int = 100
    content_digest: str = ""

    def __post_init__(self) -> None:
        _require_id(self.key, "key")
        _require_id(self.project_id, "project_id")
        if not isinstance(self.source_kind, str) or not self.source_kind:
            raise ValueError("source_kind must be non-empty")
        if self.validity not in VALIDITY_VALUES:
            raise ValueError(f"validity must be one of {VALIDITY_VALUES}")
        if self.freshness not in FRESHNESS_VALUES:
            raise ValueError(f"freshness must be one of {FRESHNESS_VALUES}")
        if self.token_mode not in TOKEN_MODES:
            raise ValueError(f"token_mode must be one of {TOKEN_MODES}")
        if self.token_count is not None and self.token_count < 0:
            raise ValueError("token_count must be >= 0")
        if self.content_digest:
            _require_digest(self.content_digest, "content_digest")
        if self.token_count is None and self.token_mode == "exact":
            object.__setattr__(self, "token_mode", "estimated")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "key": self.key,
            "project_id": self.project_id,
            "source_ref": self.source_ref.to_dict(),
            "source_kind": self.source_kind,
            "validity": self.validity,
            "freshness": self.freshness,
            "priority": self.priority,
            "content_digest": self.content_digest,
        }
        if self.token_count is not None:
            d["token_count"] = str(self.token_count)
            d["token_mode"] = self.token_mode
        return d


@dataclass(frozen=True)
class ContextRequest:
    project_id: str
    task_id: str
    attempt_id: str
    purpose: str
    model_context_limit: int
    output_reserve: int
    token_budget: int
    mandatory_refs: tuple[str, ...] = ()
    query: str = ""
    allowed_shared_scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.project_id, "project_id")
        _require_id(self.task_id, "task_id")
        _require_id(self.attempt_id, "attempt_id")
        if not isinstance(self.purpose, str) or not self.purpose:
            raise ValueError("purpose must be non-empty")
        for v in (self.model_context_limit, self.output_reserve, self.token_budget):
            if not isinstance(v, int) or v < 0:
                raise ValueError("budget values must be non-negative ints")
        if self.output_reserve > self.model_context_limit:
            raise ValueError("output_reserve exceeds model_context_limit")
        if self.token_budget > self.model_context_limit - self.output_reserve:
            raise ValueError("token_budget exceeds available context (limit - reserve)")
        for ref in self.mandatory_refs:
            _require_id(ref, "mandatory_ref")


@dataclass(frozen=True)
class ContextSelection:
    key: str
    project_id: str
    source_ref: ObjectRef
    source_kind: str
    validity: str
    freshness: str
    token_count: int
    token_mode: str
    priority: int
    content_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "project_id": self.project_id,
            "source_ref": self.source_ref.to_dict(),
            "source_kind": self.source_kind,
            "validity": self.validity,
            "freshness": self.freshness,
            "token_count": str(self.token_count),
            "token_mode": self.token_mode,
            "priority": self.priority,
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class ContextExclusion:
    key: str
    reason: str
    source_ref: Optional[ObjectRef] = None
    project_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"key": self.key, "reason": self.reason,
                             "project_id": self.project_id}
        if self.source_ref is not None:
            d["source_ref"] = self.source_ref.to_dict()
        return d


@dataclass(frozen=True)
class ContextManifest:
    schema_version: str
    canonicalization: str
    project_id: str
    task_id: str
    attempt_id: str
    purpose: str
    token_budget: int
    token_used: int
    token_estimation: str
    selections: tuple[ContextSelection, ...]
    exclusions: tuple[ContextExclusion, ...]

    def body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonicalization": self.canonicalization,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "purpose": self.purpose,
            "token_budget": str(self.token_budget),
            "token_used": str(self.token_used),
            "token_estimation": self.token_estimation,
            "selections": [s.to_dict() for s in self.selections],
            "exclusions": [e.to_dict() for e in self.exclusions],
        }

    def digest(self) -> str:
        return sha256_digest(self.body())

    def to_dict(self) -> dict[str, Any]:
        d = self.body()
        d["digest"] = self.digest()
        return d


# --- knowledge revisions & feedback -------------------------------------------

@dataclass(frozen=True)
class KnowledgeRevision:
    scope: str = "project"
    title: str = ""
    claim: str = ""
    source_refs: tuple[ObjectRef, ...] = ()
    valid_conditions: tuple[str, ...] = ()
    invalidated_by: tuple[str, ...] = ()
    status: str = "candidate"
    sensitivity: str = "internal"
    sharing_policy: str = "project"

    def __post_init__(self) -> None:
        if self.scope not in KNOWLEDGE_SCOPES:
            raise ValueError(f"scope must be one of {KNOWLEDGE_SCOPES}")
        if self.status not in KNOWLEDGE_STATUSES:
            raise ValueError(f"status must be one of {KNOWLEDGE_STATUSES}")
        if not isinstance(self.title, str) or not self.title:
            raise ValueError("title must be non-empty")
        if not isinstance(self.claim, str) or not self.claim:
            raise ValueError("claim must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "title": self.title,
            "claim": self.claim,
            "source_refs": _object_refs_to_dicts(self.source_refs),
            "valid_conditions": list(self.valid_conditions),
            "invalidated_by": list(self.invalidated_by),
            "status": self.status,
            "sensitivity": self.sensitivity,
            "sharing_policy": self.sharing_policy,
        }


@dataclass(frozen=True)
class UseEvent:
    """An actual use/injection/adoption of a knowledge revision.

    `source_use_key` is the stable dedup identity of this event (design 02:
    use_event with UNIQUE(source request/ref)). Retrieval count is never a
    quality signal; only an explicit adopted/injected event contributes.
    """

    source_use_key: str
    use_kind: str
    knowledge_ref: ObjectRef
    project_id: str = ""
    context_ref: Optional[ObjectRef] = None
    at_seq: str = "0"

    def __post_init__(self) -> None:
        _require_id(self.source_use_key, "source_use_key")
        if self.use_kind not in USE_KINDS:
            raise ValueError(f"use_kind must be one of {USE_KINDS}")
        if self.project_id:
            _require_id(self.project_id, "project_id")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source_use_key": self.source_use_key,
            "use_kind": self.use_kind,
            "knowledge_ref": self.knowledge_ref.to_dict(),
            "project_id": self.project_id,
            "at_seq": self.at_seq,
        }
        if self.context_ref is not None:
            d["context_ref"] = self.context_ref.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UseEvent":
        return cls(
            source_use_key=data["source_use_key"],
            use_kind=data["use_kind"],
            knowledge_ref=ObjectRef.from_dict(data["knowledge_ref"]),
            project_id=data.get("project_id", ""),
            context_ref=ObjectRef.from_dict(data["context_ref"])
            if data.get("context_ref") is not None else None,
            at_seq=data.get("at_seq", "0"),
        )


@dataclass(frozen=True)
class OutcomeEvent:
    """A verified outcome feeding back into knowledge scoring.

    `source_outcome_key` is the stable dedup identity (design 02: outcome with
    UNIQUE(source outcome key)). `use_source_key` links a rollback/correction to
    the original adopted use so it stays traceable instead of being silently
    re-scored.
    """

    source_outcome_key: str
    outcome_kind: str
    project_id: str = ""
    use_source_key: str = ""
    verified_result_ref: Optional[ObjectRef] = None
    at_seq: str = "0"

    def __post_init__(self) -> None:
        _require_id(self.source_outcome_key, "source_outcome_key")
        if self.outcome_kind not in OUTCOME_KINDS:
            raise ValueError(f"outcome_kind must be one of {OUTCOME_KINDS}")
        if self.project_id:
            _require_id(self.project_id, "project_id")
        if self.use_source_key:
            _require_id(self.use_source_key, "use_source_key")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source_outcome_key": self.source_outcome_key,
            "outcome_kind": self.outcome_kind,
            "project_id": self.project_id,
            "use_source_key": self.use_source_key,
            "at_seq": self.at_seq,
        }
        if self.verified_result_ref is not None:
            d["verified_result_ref"] = self.verified_result_ref.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutcomeEvent":
        return cls(
            source_outcome_key=data["source_outcome_key"],
            outcome_kind=data["outcome_kind"],
            project_id=data.get("project_id", ""),
            use_source_key=data.get("use_source_key", ""),
            verified_result_ref=ObjectRef.from_dict(data["verified_result_ref"])
            if data.get("verified_result_ref") is not None else None,
            at_seq=data.get("at_seq", "0"),
        )


@dataclass(frozen=True)
class ScoreDelta:
    source_key: str
    kind: str
    delta: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"source_key": self.source_key, "kind": self.kind,
                "delta": str(self.delta), "reason": self.reason}


@dataclass(frozen=True)
class ScoreRecord:
    score_version: str
    score: float
    causal_refs: tuple[str, ...]
    trace: tuple[ScoreDelta, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_version": self.score_version,
            "score": str(self.score),
            "causal_refs": list(self.causal_refs),
            "trace": [d.to_dict() for d in self.trace],
        }


@dataclass(frozen=True)
class PromotionTask:
    """Explicit human-reviewed project -> shared promotion (design 05 §1)."""

    knowledge_ref: ObjectRef
    reviewed_scope: str = "shared"
    human_decision_ref: Optional[ObjectRef] = None
    target_store_id: str = ""
    state: str = "pending"
    shared_ref: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.reviewed_scope not in KNOWLEDGE_SCOPES:
            raise ValueError(f"reviewed_scope must be one of {KNOWLEDGE_SCOPES}")
        if self.state not in ("pending", "copied", "completed", "failed"):
            raise ValueError("state must be pending|copied|completed|failed")
        if self.target_store_id:
            _require_id(self.target_store_id, "target_store_id")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "knowledge_ref": self.knowledge_ref.to_dict(),
            "reviewed_scope": self.reviewed_scope,
            "state": self.state,
            "target_store_id": self.target_store_id,
        }
        if self.human_decision_ref is not None:
            d["human_decision_ref"] = self.human_decision_ref.to_dict()
        if self.shared_ref is not None:
            d["shared_ref"] = self.shared_ref
        return d


@dataclass(frozen=True)
class FeedbackReceipt:
    """Result of settling a use/outcome into the scoring ledger."""

    event_key: str
    score_version: str
    new_score: float
    causal_refs: tuple[str, ...]
    duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key,
            "score_version": self.score_version,
            "new_score": str(self.new_score),
            "causal_refs": list(self.causal_refs),
            "duplicate": self.duplicate,
        }
