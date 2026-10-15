"""P09 dataset and script-retention data types.

The corpus layer holds no SQL and no model-training code. It turns already
traceable facts into an immutable, purpose-bound dataset manifest, keeps the
human quality review strictly separate from the export authorization, and only
ever *plans* artifact cleanup (never deletes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..contracts import ObjectRef, sha256_digest

SAMPLE_KINDS: tuple[str, ...] = ("success", "failure", "correction", "preference", "tool")
SPLITS: tuple[str, ...] = ("train", "eval", "test")
REVIEW_VERDICTS: tuple[str, ...] = ("accepted", "rejected")
ARTIFACT_CLASSES: tuple[str, ...] = ("golden", "temp", "failure_bundle", "reports")
REVIEW_STATUS_CANDIDATE = "candidate"
REVIEW_STATUS_REVIEWED = "reviewed"

#: Placeholder content that must never be counted as a validated success.
EMPTY_TEMPLATES: frozenset[str] = frozenset(
    {"", "todo", "tbd", "n/a", "na", "none", "null", "{}", "[]", "<empty>", "placeholder", "fixme"}
)

EXCLUSION_REASONS: tuple[str, ...] = (
    "EMPTY_TEMPLATE", "UNRESOLVED_REPAIR", "UNKNOWN_OUTCOME", "FAILURE_NOT_ALLOWED",
    "KIND_NOT_ALLOWED", "SENSITIVITY_NOT_ALLOWED", "SOURCE_INCOMPLETE",
    "MISSING_REDACTION_RECEIPT", "MISSING_QUALITY_LABEL", "SPLIT_NOT_ALLOWED",
    "SPLIT_ASSIGNMENT_MISMATCH", "DUPLICATE_CONTENT", "TASK_LIMIT_EXCEEDED",
    "REVIEW_REJECTED",
)


def is_empty_template(value: Any) -> bool:
    """True for missing or placeholder content."""
    if value is None:
        return True
    if isinstance(value, bytes):
        return not value.strip()
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0
    if isinstance(value, str):
        return value.strip().lower() in EMPTY_TEMPLATES
    return False


@dataclass(frozen=True)
class SplitSpec:
    """Frozen `dataset.build.split_spec`: lineage grouping plus a fixed seed."""

    group_by: str = "project_task_lineage"
    seed: str = "1"
    train_percent: int = 80
    eval_percent: int = 10
    test_percent: int = 10

    def __post_init__(self) -> None:
        if self.group_by != "project_task_lineage":
            raise ValueError("group_by must be project_task_lineage")
        if not str(self.seed).isdigit():
            raise ValueError("seed must be a non-negative integer string")
        for label, value in (("train_percent", self.train_percent),
                             ("eval_percent", self.eval_percent),
                             ("test_percent", self.test_percent)):
            if not 0 <= int(value) <= 100:
                raise ValueError(f"{label} must be between 0 and 100")
        if int(self.train_percent) + int(self.eval_percent) + int(self.test_percent) != 100:
            raise ValueError("split percentages must sum to 100")

    def to_dict(self) -> dict[str, Any]:
        return {"group_by": self.group_by, "seed": str(self.seed),
                "train_percent": int(self.train_percent),
                "eval_percent": int(self.eval_percent),
                "test_percent": int(self.test_percent)}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SplitSpec":
        return cls(group_by=payload["group_by"], seed=str(payload["seed"]),
                   train_percent=int(payload["train_percent"]),
                   eval_percent=int(payload["eval_percent"]),
                   test_percent=int(payload["test_percent"]))


@dataclass(frozen=True)
class DatasetPolicy:
    """Fixed purpose/authorization, level, redaction, quality and split rules."""

    dataset_id: str
    purpose: str
    policy_revision: str = "pol-1"
    allowed_kinds: tuple[str, ...] = SAMPLE_KINDS
    allowed_splits: tuple[str, ...] = SPLITS
    allowed_sensitivity: tuple[str, ...] = ("public", "internal")
    allowed_failure_types: tuple[str, ...] = ()
    required_quality_labels: tuple[str, ...] = ()
    require_redaction_receipt: bool = True
    min_source_refs: int = 1
    allow_failures: bool = True
    deduplicate_content: bool = True
    redaction_revision: str = "redact-1"
    redact_fields: tuple[str, ...] = ()
    max_samples_per_task: int | None = None

    def __post_init__(self) -> None:
        if not self.dataset_id or not self.purpose:
            raise ValueError("dataset_id and purpose are required")
        if not self.allowed_kinds or not set(self.allowed_kinds) <= set(SAMPLE_KINDS):
            raise ValueError("allowed_kinds must contain only known sample kinds")
        if not self.allowed_splits or not set(self.allowed_splits) <= set(SPLITS):
            raise ValueError("allowed_splits must contain only train/eval/test")
        if self.min_source_refs < 1:
            raise ValueError("min_source_refs must be at least 1")
        if self.max_samples_per_task is not None and self.max_samples_per_task < 1:
            raise ValueError("max_samples_per_task must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id, "purpose": self.purpose,
            "policy_revision": self.policy_revision,
            "allowed_kinds": list(self.allowed_kinds), "allowed_splits": list(self.allowed_splits),
            "allowed_sensitivity": list(self.allowed_sensitivity),
            "allowed_failure_types": list(self.allowed_failure_types),
            "required_quality_labels": list(self.required_quality_labels),
            "require_redaction_receipt": self.require_redaction_receipt,
            "min_source_refs": self.min_source_refs, "allow_failures": self.allow_failures,
            "deduplicate_content": self.deduplicate_content,
            "redaction_revision": self.redaction_revision,
            "redact_fields": list(self.redact_fields),
            "max_samples_per_task": self.max_samples_per_task,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DatasetPolicy":
        return cls(
            dataset_id=str(payload["dataset_id"]), purpose=str(payload["purpose"]),
            policy_revision=str(payload.get("policy_revision", "pol-1")),
            allowed_kinds=tuple(payload.get("allowed_kinds", SAMPLE_KINDS)),
            allowed_splits=tuple(payload.get("allowed_splits", SPLITS)),
            allowed_sensitivity=tuple(payload.get("allowed_sensitivity", ("public", "internal"))),
            allowed_failure_types=tuple(payload.get("allowed_failure_types", ())),
            required_quality_labels=tuple(payload.get("required_quality_labels", ())),
            require_redaction_receipt=bool(payload.get("require_redaction_receipt", True)),
            min_source_refs=int(payload.get("min_source_refs", 1)),
            allow_failures=bool(payload.get("allow_failures", True)),
            deduplicate_content=bool(payload.get("deduplicate_content", True)),
            redaction_revision=str(payload.get("redaction_revision", "redact-1")),
            redact_fields=tuple(payload.get("redact_fields", ())),
            max_samples_per_task=payload.get("max_samples_per_task"),
        )

    def digest(self) -> str:
        return sha256_digest(self.to_dict())


@dataclass(frozen=True)
class Sample:
    """One candidate sample with exact provenance; never carries review claims.

    Human review and export authorization are deliberately *not* fields here: a
    caller cannot label its own sample as reviewed or authorized.
    """

    sample_id: str
    kind: str
    group_id: str
    source_refs: tuple[ObjectRef, ...]
    input: Any = ""
    output: Any = ""
    source_digests: tuple[str, ...] = ()
    artifacts: tuple[ObjectRef, ...] = ()
    verification_labels: tuple[str, ...] = ()
    failure_type: str | None = None
    sensitivity: str = "internal"
    redaction_receipt: str | None = None
    quality_flags: tuple[str, ...] = ()
    split: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sample_id or not self.group_id:
            raise ValueError("sample_id and group_id are required")
        if self.kind not in SAMPLE_KINDS:
            raise ValueError(f"unknown sample kind {self.kind!r}")
        if self.split is not None and self.split not in SPLITS:
            raise ValueError(f"unknown split {self.split!r}")

    def content(self) -> dict[str, Any]:
        return {"input": self.input, "output": self.output}

    def content_digest(self) -> str:
        return sha256_digest(self.content())

    def digest(self) -> str:
        return sha256_digest({
            "sample_id": self.sample_id, "kind": self.kind, "group_id": self.group_id,
            "content_digest": self.content_digest(),
            "source_refs": [r.to_dict() for r in self.source_refs],
            "source_digests": list(self.source_digests),
            "failure_type": self.failure_type,
        })

    def to_payload(self) -> dict[str, Any]:
        """The internal `sample` revision payload written by a trusted writer."""
        return {
            "sample_id": self.sample_id, "kind": self.kind, "group_id": self.group_id,
            "input": self.input, "output": self.output,
            "source_refs": [r.to_dict() for r in self.source_refs],
            "source_digests": list(self.source_digests),
            "artifacts": [r.to_dict() for r in self.artifacts],
            "verification_labels": list(self.verification_labels),
            "failure_type": self.failure_type, "sensitivity": self.sensitivity,
            "redaction_receipt": self.redaction_receipt,
            "quality_flags": list(self.quality_flags),
            "split": self.split, "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Sample":
        return cls(
            sample_id=str(payload["sample_id"]), kind=str(payload["kind"]),
            group_id=str(payload["group_id"]),
            source_refs=tuple(ObjectRef.from_dict(r) for r in payload.get("source_refs", ())),
            input=payload.get("input", ""), output=payload.get("output", ""),
            source_digests=tuple(payload.get("source_digests", ())),
            artifacts=tuple(ObjectRef.from_dict(r) for r in payload.get("artifacts", ())),
            verification_labels=tuple(payload.get("verification_labels", ())),
            failure_type=payload.get("failure_type"),
            sensitivity=str(payload.get("sensitivity", "internal")),
            redaction_receipt=payload.get("redaction_receipt"),
            quality_flags=tuple(payload.get("quality_flags", ())),
            split=payload.get("split"),
            metadata=payload.get("metadata") or {},
        )


@dataclass(frozen=True)
class SampleReview:
    """A human per-sample quality review (separate from export authorization)."""

    sample_id: str
    verdict: str
    reason: str
    reviewer_id: str
    is_human: bool = True

    def __post_init__(self) -> None:
        if self.verdict not in REVIEW_VERDICTS:
            raise ValueError(f"verdict must be one of {REVIEW_VERDICTS}")
        if not self.reason or not self.reviewer_id:
            raise ValueError("reason and reviewer_id are required")

    def to_dict(self) -> dict[str, Any]:
        return {"sample_id": self.sample_id, "verdict": self.verdict, "reason": self.reason,
                "reviewer_id": self.reviewer_id, "is_human": self.is_human}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, reviewer_id: str | None = None,
                     is_human: bool = True) -> "SampleReview":
        return cls(sample_id=str(payload["sample_id"]), verdict=str(payload["verdict"]),
                   reason=str(payload["reason"]),
                   reviewer_id=str(reviewer_id or payload.get("reviewer_id") or ""),
                   is_human=bool(payload.get("is_human", is_human)))


@dataclass(frozen=True)
class Exclusion:
    """A candidate sample kept out of the dataset, with a visible reason."""

    sample_id: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"sample_id": self.sample_id, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class DatasetManifest:
    """Immutable dataset manifest revision body (published once per version)."""

    dataset_id: str
    policy_revision: str
    policy_digest: str
    policy_ref: Mapping[str, Any] | None
    purpose: str
    purpose_ref: Mapping[str, Any] | None
    source_as_of: str
    split_spec: Mapping[str, Any]
    review_status: str
    samples: tuple[Mapping[str, Any], ...]
    sample_digests: tuple[str, ...]
    exclusions: tuple[Mapping[str, Any], ...]
    exclusion_stats: Mapping[str, int]
    counts: Mapping[str, int]
    completeness: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "p09.dataset_manifest.v1",
            "dataset_id": self.dataset_id,
            "policy_revision": self.policy_revision,
            "policy_digest": self.policy_digest,
            "policy_ref": dict(self.policy_ref) if self.policy_ref else None,
            "purpose": self.purpose,
            "purpose_ref": dict(self.purpose_ref) if self.purpose_ref else None,
            "source_as_of": self.source_as_of,
            "split_spec": dict(self.split_spec),
            "review_status": self.review_status,
            "sample_count": len(self.samples),
            "sample_digests": list(self.sample_digests),
            "samples": [dict(row) for row in self.samples],
            "exclusions": [dict(row) for row in self.exclusions],
            "exclusion_stats": dict(self.exclusion_stats),
            "counts": dict(self.counts),
            "completeness": dict(self.completeness),
        }

    def digest(self) -> str:
        return sha256_digest(self.to_dict())

    def candidate_samples(self) -> tuple[Sample, ...]:
        """Reconstruct the typed candidates of this manifest (for review/export)."""
        return tuple(Sample.from_payload(row) for row in self.samples)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DatasetManifest":
        return cls(
            dataset_id=str(data["dataset_id"]),
            policy_revision=str(data.get("policy_revision", "")),
            policy_digest=str(data.get("policy_digest", "")),
            policy_ref=data.get("policy_ref"), purpose=str(data.get("purpose", "")),
            purpose_ref=data.get("purpose_ref"),
            source_as_of=str(data.get("source_as_of", "")),
            split_spec=data.get("split_spec") or {},
            review_status=str(data.get("review_status", REVIEW_STATUS_CANDIDATE)),
            samples=tuple(data.get("samples", ())),
            sample_digests=tuple(data.get("sample_digests", ())),
            exclusions=tuple(data.get("exclusions", ())),
            exclusion_stats=data.get("exclusion_stats") or {},
            counts=data.get("counts") or {}, completeness=data.get("completeness") or {},
        )


@dataclass(frozen=True)
class ExportReceipt:
    """Separate export receipt; publishing a version never overwrites another."""

    dataset_id: str
    version: str
    manifest_digest: str
    artifact_digest: str
    sample_count: int
    sink_id: str
    files: tuple[str, ...]
    human_decision_ref: ObjectRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"dataset_id": self.dataset_id, "version": self.version,
                "manifest_digest": self.manifest_digest, "artifact_digest": self.artifact_digest,
                "sample_count": self.sample_count, "sink_id": self.sink_id,
                "files": list(self.files),
                "human_decision_ref": (self.human_decision_ref.to_dict()
                                       if self.human_decision_ref else None)}


@dataclass(frozen=True)
class ScriptTestResult:
    name: str
    status: str          # passed / failed / not_run
    evidence_digest: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status,
                "evidence_digest": self.evidence_digest, "detail": self.detail}


@dataclass(frozen=True)
class ScriptArtifact:
    """A script as an artifact: usage, schemas, environment, permissions, origin.

    The kernel only *proposes* promotion; it never registers a script as a
    trusted tool on its own.
    """

    script_id: str
    purpose: str
    source_attempt_ref: ObjectRef
    source_digest: str
    input_schema_ref: str
    output_schema_ref: str
    runtime_env: Mapping[str, Any]
    permissions: tuple[str, ...]
    test_results: tuple[ScriptTestResult, ...] = ()
    reuse_results: tuple[str, ...] = ()
    retention_class: str = "standard"

    def __post_init__(self) -> None:
        if not self.script_id or not self.purpose or not self.source_digest:
            raise ValueError("script_id, purpose and source_digest are required")

    @property
    def promotion_eligible(self) -> bool:
        """Only a script with real, non-failing test evidence is proposed."""
        return bool(self.test_results) and all(
            r.status == "passed" and r.evidence_digest for r in self.test_results)

    def promotion_status(self) -> str:
        return "candidate" if self.promotion_eligible else "not_eligible"

    def to_payload(self) -> dict[str, Any]:
        return {"script_id": self.script_id, "purpose": self.purpose,
                "source_attempt_ref": self.source_attempt_ref.to_dict(),
                "source_digest": self.source_digest,
                "input_schema_ref": self.input_schema_ref,
                "output_schema_ref": self.output_schema_ref,
                "runtime_env": dict(self.runtime_env), "permissions": list(self.permissions),
                "test_results": [r.to_dict() for r in self.test_results],
                "reuse_results": list(self.reuse_results),
                "retention_class": self.retention_class,
                "promotion_status": self.promotion_status()}

    def digest(self) -> str:
        return sha256_digest(self.to_payload())


@dataclass(frozen=True)
class CleanupEntry:
    script_id: str
    decision: str                 # keep / eligible_for_removal
    reasons: tuple[str, ...]
    referenced_by: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"script_id": self.script_id, "decision": self.decision,
                "reasons": list(self.reasons), "referenced_by": list(self.referenced_by)}


@dataclass(frozen=True)
class CleanupPlan:
    """v1 cleanup output: candidates and retention reasons only, never deletion."""

    retention_policy_ref: str
    as_of_seq: str
    entries: tuple[CleanupEntry, ...]
    deletions_performed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"retention_policy_ref": self.retention_policy_ref, "as_of_seq": self.as_of_seq,
                "entries": [e.to_dict() for e in self.entries],
                "deletions_performed": self.deletions_performed,
                "deletion_mode": "plan_only"}


@dataclass(frozen=True)
class Tombstone:
    """Deleting sensitive output keeps the hash; history is never rewritten."""

    object_type: str
    object_id: str
    digest: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"object_type": self.object_type, "object_id": self.object_id,
                "digest": self.digest, "reason": self.reason, "state": "deleted"}


@dataclass(frozen=True)
class CorpusArtifact:
    artifact_id: str
    artifact_class: str
    digest: str
    source_refs: tuple[ObjectRef, ...] = ()
    usage_manifest: Mapping[str, Any] = field(default_factory=dict)
    collected_from: str = ""

    def __post_init__(self) -> None:
        if self.artifact_class not in ARTIFACT_CLASSES:
            raise ValueError(f"unknown artifact class {self.artifact_class!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"artifact_id": self.artifact_id, "artifact_class": self.artifact_class,
                "digest": self.digest, "source_refs": [r.to_dict() for r in self.source_refs],
                "usage_manifest": dict(self.usage_manifest),
                "collected_from": self.collected_from}


def corpus_eligibility(artifact: CorpusArtifact) -> tuple[bool, str]:
    """Only provenance-carrying fixtures with a usage manifest become candidates.

    Pytest temp databases, scratch output and blanket log dumps are rejected.
    """
    if artifact.artifact_class == "temp":
        return False, "pytest temp databases and scratch output are never corpus"
    if not artifact.digest:
        return False, "artifact has no content digest"
    if not artifact.source_refs:
        return False, "artifact has no exact source revision"
    if artifact.artifact_class == "reports" and not artifact.usage_manifest:
        return False, "reports need a provenance+usage manifest to become candidates"
    return True, ""


def summarize_reviews(reviews: Sequence[SampleReview]) -> dict[str, int]:
    summary = {verdict: 0 for verdict in REVIEW_VERDICTS}
    for review in reviews:
        summary[review.verdict] += 1
    return summary
