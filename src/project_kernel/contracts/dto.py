"""Typed v1 DTOs.

Generated from contracts/v1 common.schema.json $defs plus the internal
capability types (09). All identifiers, sequences and digests are validated on
construction so no arbitrary dict can slip into the service layer. Inbound JSON
is validated by contracts.validation before these DTOs are constructed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SEQ_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")


def _require_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"{name} must match {_ID_RE.pattern!r}, got {value!r}")
    return value


def _require_seq(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SEQ_RE.match(value):
        raise ValueError(f"{name} must be a decimal string, got {value!r}")
    return value


def _require_digest(value: str, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.match(value):
        raise ValueError(f"{name} must be a 64-char lowercase sha256 hex, got {value!r}")
    return value


def _enum_value(value: Any, name: str) -> str:
    if isinstance(value, str):
        return value
    if hasattr(value, "value"):
        return value.value
    raise ValueError(f"{name} must be a str or Enum, got {value!r}")


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ObjectRef:
    project_id: str
    object_type: str
    object_id: str
    revision_id: str

    def __post_init__(self) -> None:
        _require_id(self.project_id, "project_id")
        _require_id(self.object_type, "object_type")
        _require_id(self.object_id, "object_id")
        _require_id(self.revision_id, "revision_id")

    def to_dict(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "revision_id": self.revision_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObjectRef":
        return cls(data["project_id"], data["object_type"], data["object_id"], data["revision_id"])


@dataclass(frozen=True)
class SharedKnowledgeRef:
    store_id: str
    object_id: str
    revision_id: str
    digest: str

    def __post_init__(self) -> None:
        _require_id(self.store_id, "store_id")
        _require_id(self.object_id, "object_id")
        _require_id(self.revision_id, "revision_id")
        _require_digest(self.digest, "digest")

    def to_dict(self) -> dict[str, str]:
        return {"store_id": self.store_id, "object_id": self.object_id,
                "revision_id": self.revision_id, "digest": self.digest}


@dataclass(frozen=True)
class Cursor:
    commit_seq: str
    event_index: int

    def __post_init__(self) -> None:
        _require_seq(self.commit_seq, "commit_seq")
        if not isinstance(self.event_index, int) or self.event_index < 0:
            raise ValueError(f"event_index must be a non-negative int, got {self.event_index!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"commit_seq": self.commit_seq, "event_index": self.event_index}


@dataclass(frozen=True)
class Selector:
    project_id: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    attempt_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_id(self.project_id, "project_id")
        for name in ("workspace_id", "session_id", "task_id", "attempt_id"):
            v = getattr(self, name)
            if v is not None:
                _require_id(v, name)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"project_id": self.project_id}
        for name in ("workspace_id", "session_id", "task_id", "attempt_id"):
            v = getattr(self, name)
            if v is not None:
                d[name] = v
        return d


@dataclass(frozen=True)
class ExpectedHead:
    object_ref: ObjectRef
    pointer_name: str
    expected_head_version: str

    def __post_init__(self) -> None:
        _require_seq(self.expected_head_version, "expected_head_version")

    def to_dict(self) -> dict[str, Any]:
        return {"object_ref": self.object_ref.to_dict(), "pointer_name": self.pointer_name,
                "expected_head_version": self.expected_head_version}


@dataclass(frozen=True)
class SourceKey:
    host_id: str
    origin_session_id: str
    log_generation: str
    source_seq: str

    def __post_init__(self) -> None:
        _require_id(self.host_id, "host_id")
        _require_id(self.origin_session_id, "origin_session_id")
        _require_id(self.log_generation, "log_generation")
        _require_seq(self.source_seq, "source_seq")

    def to_dict(self) -> dict[str, str]:
        return {"host_id": self.host_id, "origin_session_id": self.origin_session_id,
                "log_generation": self.log_generation, "source_seq": self.source_seq}


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    sha256: str
    size_bytes: str
    media_type: str
    required: bool

    def __post_init__(self) -> None:
        _require_id(self.artifact_id, "artifact_id")
        _require_digest(self.sha256, "sha256")
        _require_seq(self.size_bytes, "size_bytes")
        if not isinstance(self.media_type, str) or not self.media_type:
            raise ValueError("media_type must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_id": self.artifact_id, "sha256": self.sha256,
                "size_bytes": self.size_bytes, "media_type": self.media_type,
                "required": self.required}


@dataclass(frozen=True)
class Amount:
    value: str
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("amount.value must be a decimal string")

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class AcceptanceItem:
    item_id: str
    requirement_ref: ObjectRef
    recipe_ref: ObjectRef
    required: bool
    evidence_type: str
    criterion: str

    def __post_init__(self) -> None:
        _require_id(self.item_id, "item_id")

    def to_dict(self) -> dict[str, Any]:
        return {"item_id": self.item_id,
                "requirement_ref": self.requirement_ref.to_dict(),
                "recipe_ref": self.recipe_ref.to_dict(),
                "required": self.required,
                "evidence_type": self.evidence_type,
                "criterion": self.criterion}


@dataclass(frozen=True)
class Strategy:
    strategy_id: str
    title: str
    hypothesis: str
    risks: tuple[str, ...] = ()
    acceptance_refs: tuple[ObjectRef, ...] = ()
    environment_requirements: tuple[ObjectRef, ...] = ()
    budget_ref: Optional[ObjectRef] = None

    def __post_init__(self) -> None:
        _require_id(self.strategy_id, "strategy_id")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "strategy_id": self.strategy_id, "title": self.title, "hypothesis": self.hypothesis,
            "risks": list(self.risks),
            "acceptance_refs": [r.to_dict() for r in self.acceptance_refs],
            "environment_requirements": [r.to_dict() for r in self.environment_requirements],
        }
        if self.budget_ref is not None:
            d["budget_ref"] = self.budget_ref.to_dict()
        return d


@dataclass(frozen=True)
class RecipeParameter:
    name: str
    value: str

    def __post_init__(self) -> None:
        _require_id(self.name, "name")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "value": self.value}


@dataclass(frozen=True)
class Recipe:
    recipe_ref: ObjectRef
    parameters: tuple[RecipeParameter, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"recipe_ref": self.recipe_ref.to_dict(),
                "parameters": [p.to_dict() for p in self.parameters]}


@dataclass(frozen=True)
class ExecutionScope:
    execution_root_ref: ObjectRef
    read_paths: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ()
    network_policy_ref: Optional[ObjectRef] = None
    required_sandbox_level: str = "none"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "execution_root_ref": self.execution_root_ref.to_dict(),
            "read_paths": list(self.read_paths),
            "write_paths": list(self.write_paths),
            "required_sandbox_level": self.required_sandbox_level,
        }
        if self.network_policy_ref is not None:
            d["network_policy_ref"] = self.network_policy_ref.to_dict()
        return d


@dataclass(frozen=True)
class Condition:
    """One of all/any/not/path-operator-value; exactly one variant must be set."""

    all: Optional[tuple["Condition", ...]] = None
    any: Optional[tuple["Condition", ...]] = None
    not_: Optional["Condition"] = None
    path: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        if self.all is not None:
            return {"all": [c.to_dict() for c in self.all]}
        if self.any is not None:
            return {"any": [c.to_dict() for c in self.any]}
        if self.not_ is not None:
            return {"not": self.not_.to_dict()}
        if self.path is not None:
            return {"path": self.path, "operator": self.operator, "value": self.value}
        raise ValueError("Condition has no variant set")


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    enabled: bool
    when: Condition
    effect: str
    reason: str

    def __post_init__(self) -> None:
        _require_id(self.rule_id, "rule_id")

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "enabled": self.enabled, "when": self.when.to_dict(),
                "effect": self.effect, "reason": self.reason}


@dataclass(frozen=True)
class ResultSource:
    kind: str
    source_key: Optional[SourceKey] = None
    payload_digest: Optional[str] = None
    provider_id: Optional[str] = None
    run_id: Optional[str] = None
    result_id: Optional[str] = None
    epoch: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind == "session_event":
            if self.source_key is None or self.payload_digest is None:
                raise ValueError("session_event requires source_key and payload_digest")
        elif self.kind == "provider_result":
            for name in ("provider_id", "run_id", "result_id", "epoch", "payload_digest"):
                if getattr(self, name) is None:
                    raise ValueError(f"provider_result requires {name}")
        else:
            raise ValueError(f"unknown result source kind {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "session_event":
            return {"kind": "session_event", "source_key": self.source_key.to_dict(),
                    "payload_digest": self.payload_digest}
        return {"kind": "provider_result", "provider_id": self.provider_id, "run_id": self.run_id,
                "result_id": self.result_id, "epoch": self.epoch, "payload_digest": self.payload_digest}


# --- Internal capability types (09) -------------------------------------------------

@dataclass(frozen=True)
class ResolvedScope:
    """Constructed only by the trusted entry point; never JSON-deserialized as trusted."""

    project_id: str
    store_id: str
    principal_id: str
    capabilities: frozenset[str]
    mode: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    attempt_id: Optional[str] = None
    resolved_config_ref: Optional[ObjectRef] = None
    rule_refs: tuple[ObjectRef, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.project_id, "project_id")
        _require_id(self.store_id, "store_id")
        _require_id(self.principal_id, "principal_id")

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class CommandContext:
    scope: ResolvedScope
    command_id: str
    idempotency_key: str
    input_hash: str
    expected_heads: tuple[ExpectedHead, ...] = ()
    source: Optional[ResultSource] = None

    def __post_init__(self) -> None:
        _require_id(self.command_id, "command_id")
        _require_id(self.idempotency_key, "idempotency_key")
        _require_digest(self.input_hash, "input_hash")


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    supported_actions: tuple[str, ...] = ()
    supported_sandbox_level: str = "unknown"
    can_cancel: bool = False
    can_query_effect: bool = False
    idempotent_apply: bool = False
    external_fencing: bool = False
    durable_result: bool = False
    model_usage_available: bool = False

    def __post_init__(self) -> None:
        _require_id(self.provider_id, "provider_id")

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "supported_actions": list(self.supported_actions),
                "supported_sandbox_level": self.supported_sandbox_level, "can_cancel": self.can_cancel,
                "can_query_effect": self.can_query_effect, "idempotent_apply": self.idempotent_apply,
                "external_fencing": self.external_fencing, "durable_result": self.durable_result,
                "model_usage_available": self.model_usage_available}


@dataclass(frozen=True)
class ExecutionHandle:
    execution_handle_id: str
    provider_id: str
    provider_run_id: str
    attempt_id: str
    operation_id: str
    epoch: str
    started_at: str
    capabilities_ref: Optional[ObjectRef] = None

    def __post_init__(self) -> None:
        _require_id(self.execution_handle_id, "execution_handle_id")
        _require_seq(self.epoch, "epoch")


@dataclass(frozen=True)
class ExecutionOutcome:
    handle: ExecutionHandle
    status: str
    evidence_mode: str
    exit_code: Optional[int] = None
    outputs: tuple[ObjectRef, ...] = ()
    changed_artifacts: tuple[ObjectRef, ...] = ()
    error_refs: tuple[ObjectRef, ...] = ()
    test_results: tuple[ObjectRef, ...] = ()
    usage: Optional[Amount] = None
    usage_unknown_reason: Optional[str] = None
    duration_ms: Optional[int] = None
    source_refs: tuple[ObjectRef, ...] = ()
    completeness: str = "complete"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "handle": {"execution_handle_id": self.handle.execution_handle_id},
            "status": self.status, "evidence_mode": self.evidence_mode,
            "outputs": [r.to_dict() for r in self.outputs],
            "changed_artifacts": [r.to_dict() for r in self.changed_artifacts],
            "error_refs": [r.to_dict() for r in self.error_refs],
            "test_results": [r.to_dict() for r in self.test_results],
            "source_refs": [r.to_dict() for r in self.source_refs],
            "completeness": self.completeness,
        }
        if self.exit_code is not None:
            d["exit_code"] = self.exit_code
        if self.usage is not None:
            d["usage"] = self.usage.to_dict()
        if self.usage_unknown_reason is not None:
            d["usage_unknown_reason"] = self.usage_unknown_reason
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d


@dataclass(frozen=True)
class FactValue:
    known: Optional[Any] = None
    reason: Optional[str] = None
    source_ref: Optional[ObjectRef] = None
    observed_at: Optional[str] = None
    valid_until: Optional[str] = None

    @property
    def is_known(self) -> bool:
        return self.known is not None


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    recipe_ref: ObjectRef
    subject_ref: Optional[ObjectRef] = None
    candidate_digest: Optional[str] = None
    result: str = "unknown"
    evidence_refs: tuple[ObjectRef, ...] = ()
    executed_at: Optional[str] = None
    environment_ref: Optional[ObjectRef] = None
    evidence_mode: str = "test"

    def __post_init__(self) -> None:
        _require_id(self.check_id, "check_id")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"check_id": self.check_id, "recipe_ref": self.recipe_ref.to_dict(),
                             "result": self.result, "evidence_refs": [r.to_dict() for r in self.evidence_refs],
                             "evidence_mode": self.evidence_mode}
        if self.subject_ref is not None:
            d["subject_ref"] = self.subject_ref.to_dict()
        if self.candidate_digest is not None:
            d["candidate_digest"] = self.candidate_digest
        if self.executed_at is not None:
            d["executed_at"] = self.executed_at
        if self.environment_ref is not None:
            d["environment_ref"] = self.environment_ref.to_dict()
        return d


@dataclass(frozen=True)
class EffectReceipt:
    operation_id: str
    status: str
    execution_terminal: bool = False
    fence_evidence_ref: Optional[ObjectRef] = None
    artifacts: tuple[ObjectRef, ...] = ()
    verified_digest: Optional[str] = None

    def __post_init__(self) -> None:
        _require_id(self.operation_id, "operation_id")


@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    idempotency_key: str
    command: str
    status: str
    commit_seq: str
    event_cursor: Cursor
    object_refs: tuple[ObjectRef, ...] = ()
    result_refs: tuple[ObjectRef, ...] = ()
    committed_at: str = field(default_factory=_iso_utc_now)
    receipt_domain: str = "project"
    store_id: str = ""
    operation_id: Optional[str] = None
    error: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "command_id": self.command_id, "idempotency_key": self.idempotency_key,
            "command": self.command, "status": self.status, "commit_seq": self.commit_seq,
            "event_cursor": self.event_cursor.to_dict(),
            "object_refs": [r.to_dict() for r in self.object_refs],
            "result_refs": [r.to_dict() for r in self.result_refs],
            "committed_at": self.committed_at, "receipt_domain": self.receipt_domain,
            "store_id": self.store_id,
        }
        if self.operation_id is not None:
            d["operation_id"] = self.operation_id
        if self.error is not None:
            d["error"] = self.error.to_dict() if hasattr(self.error, "to_dict") else self.error
        return d


@dataclass(frozen=True)
class QueryEnvelope:
    as_of_seq: str
    projection_version: str
    computed_at: str
    source_watermarks: dict[str, Any] = field(default_factory=dict)
    freshness: str = "current"
    completeness: str = "complete"
    gaps: tuple[str, ...] = ()
    data: Any = None
    next_page_token: Optional[str] = None

    def __post_init__(self) -> None:
        _require_seq(self.as_of_seq, "as_of_seq")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "as_of_seq": self.as_of_seq, "projection_version": self.projection_version,
            "computed_at": self.computed_at, "source_watermarks": self.source_watermarks,
            "freshness": self.freshness, "completeness": self.completeness,
            "gaps": list(self.gaps), "data": self.data,
        }
        if self.next_page_token is not None:
            d["next_page_token"] = self.next_page_token
        return d


@dataclass(frozen=True)
class DeliverySnapshotBody:
    schema_version: str
    canonicalization: str
    evidence_mode: str
    project_id: str
    task_ref: ObjectRef
    selected_attempt_ref: ObjectRef
    packet_ref: ObjectRef
    requirement_refs: tuple[ObjectRef, ...]
    design_refs: tuple[ObjectRef, ...]
    acceptance_refs: tuple[ObjectRef, ...]
    rule_refs: tuple[ObjectRef, ...]
    scope_ref: ObjectRef
    input_manifest_ref: ObjectRef
    context_manifest_ref: ObjectRef
    environment_ref: ObjectRef
    verification_refs: tuple[ObjectRef, ...]
    candidate_digest: str
    delivery: dict[str, Any]
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        _require_id(self.project_id, "project_id")
        _require_digest(self.candidate_digest, "candidate_digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "canonicalization": self.canonicalization,
            "evidence_mode": self.evidence_mode, "project_id": self.project_id,
            "task_ref": self.task_ref.to_dict(), "selected_attempt_ref": self.selected_attempt_ref.to_dict(),
            "packet_ref": self.packet_ref.to_dict(),
            "requirement_refs": [r.to_dict() for r in self.requirement_refs],
            "design_refs": [r.to_dict() for r in self.design_refs],
            "acceptance_refs": [r.to_dict() for r in self.acceptance_refs],
            "rule_refs": [r.to_dict() for r in self.rule_refs],
            "scope_ref": self.scope_ref.to_dict(), "input_manifest_ref": self.input_manifest_ref.to_dict(),
            "context_manifest_ref": self.context_manifest_ref.to_dict(),
            "environment_ref": self.environment_ref.to_dict(),
            "verification_refs": [r.to_dict() for r in self.verification_refs],
            "candidate_digest": self.candidate_digest, "delivery": self.delivery,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }

    def digest(self) -> str:
        from .digest import sha256_digest
        return sha256_digest(self.to_dict())
