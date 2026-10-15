"""Candidate-manifest build and no-overwrite dataset export (P09).

`build_manifest` is pure: it filters/cleans candidates against a frozen
`DatasetPolicy`, records every exclusion with a visible reason, assigns splits by
lineage and applies the human review verdicts. `FileSystemSink` publishes one
dataset version and refuses to overwrite a published one.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..contracts import sha256_digest
from .models import (
    REVIEW_STATUS_CANDIDATE,
    DatasetManifest,
    DatasetPolicy,
    Exclusion,
    Sample,
    SampleReview,
    SplitSpec,
    is_empty_template,
)
from .splits import assign_split


class CorpusExportError(ValueError):
    """A policy boundary or lineage rule was violated by the candidate set."""


def redact(value: Any, fields: Sequence[str]) -> Any:
    """Return a redacted copy; a redacted field keeps its key, never its value."""
    names = set(fields)
    if isinstance(value, Mapping):
        return {k: "[REDACTED]" if k in names else redact(v, names) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, names) for v in value]
    return value


def _violation(policy: DatasetPolicy, sample: Sample, split: str) -> tuple[str | None, str]:
    """First policy boundary the candidate violates, if any."""
    if sample.kind not in policy.allowed_kinds:
        return "KIND_NOT_ALLOWED", f"kind {sample.kind!r} outside policy"
    if split not in policy.allowed_splits:
        return "SPLIT_NOT_ALLOWED", f"split {split!r} outside policy"
    if sample.sensitivity not in policy.allowed_sensitivity:
        return "SENSITIVITY_NOT_ALLOWED", f"sensitivity {sample.sensitivity!r} outside policy"
    if len(sample.source_refs) < policy.min_source_refs:
        return ("SOURCE_INCOMPLETE",
                f"{len(sample.source_refs)} source refs < required {policy.min_source_refs}")
    if any(not ref.object_id or not ref.revision_id for ref in sample.source_refs):
        return "SOURCE_INCOMPLETE", "source reference without an exact revision"
    if policy.require_redaction_receipt and not sample.redaction_receipt:
        return "MISSING_REDACTION_RECEIPT", "no redaction receipt for this sample"
    missing = [label for label in policy.required_quality_labels
               if label not in sample.verification_labels]
    if missing:
        return "MISSING_QUALITY_LABEL", f"missing quality labels {missing}"
    if sample.kind == "failure":
        if not policy.allow_failures:
            return "FAILURE_NOT_ALLOWED", "policy excludes failure samples"
        if policy.allowed_failure_types and sample.failure_type not in policy.allowed_failure_types:
            return "FAILURE_NOT_ALLOWED", f"failure type {sample.failure_type!r} outside policy"
    if is_empty_template(sample.input) and is_empty_template(sample.output):
        return "EMPTY_TEMPLATE", "no real content (empty template)"
    if sample.kind == "success":
        if is_empty_template(sample.input) or is_empty_template(sample.output):
            return "EMPTY_TEMPLATE", "success sample with placeholder content"
        if sample.failure_type:
            return ("UNRESOLVED_REPAIR",
                    f"success sample still carries failure_type {sample.failure_type!r}")
        unknown = sorted(set(sample.quality_flags) & {"unknown", "unresolved", "simulation"})
        if unknown:
            return "UNKNOWN_OUTCOME", f"quality flags {unknown}"
    if sample.kind == "correction" and (not sample.failure_type
                                        or sample.failure_type == "unknown"):
        return "UNRESOLVED_REPAIR", "repair sample without a known failure type"
    return None, ""


def _row(policy: DatasetPolicy, sample: Sample, split: str, content: Mapping[str, Any],
         review: SampleReview | None) -> dict[str, Any]:    return {
        "sample_id": sample.sample_id,
        "sample_digest": sample.digest(),
        "content_digest": sample.content_digest(),
        "kind": sample.kind,
        "failure_type": sample.failure_type,
        "group_id": sample.group_id,
        "split": split,
        "input": content["input"],
        "output": content["output"],
        "source_refs": [ref.to_dict() for ref in sample.source_refs],
        "source_digests": list(sample.source_digests),
        "artifacts": [ref.to_dict() for ref in sample.artifacts],
        "verification_labels": list(sample.verification_labels),
        "quality_flags": list(sample.quality_flags),
        "sensitivity": sample.sensitivity,
        "redaction_receipt": sample.redaction_receipt,
        "redaction_revision": policy.redaction_revision,
        "review": review.to_dict() if review else None,
    }


def build_manifest(policy: DatasetPolicy, samples: Iterable[Sample], *, project_id: str,
                   spec: SplitSpec, source_as_of: str,
                   purpose_ref: Mapping[str, Any] | None = None,
                   policy_ref: Mapping[str, Any] | None = None,
                   reviews: Sequence[SampleReview] = (),
                   review_status: str = REVIEW_STATUS_CANDIDATE) -> DatasetManifest:
    """Filter/clean candidates into an immutable manifest; exclusions stay visible.

    Cross-project sources and lineage split conflicts are hard errors: silently
    excluding them would hide a real isolation/leak violation.
    """
    review_by_sample = {review.sample_id: review for review in reviews}
    rows: list[dict[str, Any]] = []
    kept: list[Sample] = []
    exclusions: list[Exclusion] = []
    content_owner: dict[str, str] = {}
    per_group: dict[str, int] = {}
    counts: dict[str, int] = {
        "considered": 0, "samples": 0, "validated_success": 0, "unreviewed": 0,
        "rejected": 0, **{kind: 0 for kind in ("success", "failure", "correction",
                                               "preference", "tool")},
    }

    for sample in sorted(samples, key=lambda item: item.sample_id):
        counts["considered"] += 1
        foreign = [ref.project_id for ref in sample.source_refs if ref.project_id != project_id]
        if foreign:
            raise CorpusExportError(
                f"sample {sample.sample_id} references another project's revision: {foreign}")
        split = assign_split(spec, project_id, sample.group_id)
        reason, detail = _violation(policy, sample, split)
        if reason is None and sample.split is not None and sample.split != split:
            reason, detail = ("SPLIT_ASSIGNMENT_MISMATCH",
                              f"declared {sample.split!r}, lineage assigns {split!r}")
        if reason is None and policy.deduplicate_content:
            owner = content_owner.get(sample.content_digest())
            if owner is not None:
                reason, detail = "DUPLICATE_CONTENT", f"same content as sample {owner}"
        if reason is None and policy.max_samples_per_task is not None:
            used = per_group.get(sample.group_id, 0)
            if used >= policy.max_samples_per_task:
                reason, detail = ("TASK_LIMIT_EXCEEDED",
                                  f"{used} samples already kept for this task lineage")
        review = review_by_sample.get(sample.sample_id)
        if reason is None and review is not None and review.verdict == "rejected":
            reason, detail = "REVIEW_REJECTED", review.reason
        if reason is not None:
            exclusions.append(Exclusion(sample.sample_id, reason, detail))
            continue

        content = redact({"input": sample.input, "output": sample.output},
                         policy.redact_fields)
        content_owner[sample.content_digest()] = sample.sample_id
        per_group[sample.group_id] = per_group.get(sample.group_id, 0) + 1
        kept.append(sample)
        counts["samples"] += 1
        counts[sample.kind] += 1
        if review is None:
            counts["unreviewed"] += 1
        elif review.verdict == "accepted" and sample.kind == "success":
            counts["validated_success"] += 1
        rows.append(_row(policy, sample, split, content, review))

    exclusion_stats: dict[str, int] = {}
    for exclusion in exclusions:
        exclusion_stats[exclusion.reason] = exclusion_stats.get(exclusion.reason, 0) + 1
    reviewed = sum(1 for row in rows if row["review"])
    completeness = {
        "samples_considered": counts["considered"],
        "samples_included": len(rows),
        "samples_excluded": len(exclusions),
        "reviewed": reviewed,
        "unreviewed": counts["unreviewed"],
        "exact_source_revisions": sum(len(sample.source_refs) for sample in kept),
        "content_deduplicated": policy.deduplicate_content,
        "complete": bool(rows) and reviewed == len(rows),
    }
    return DatasetManifest(
        dataset_id=policy.dataset_id, policy_revision=policy.policy_revision,
        policy_digest=policy.digest(), policy_ref=policy_ref, purpose=policy.purpose,
        purpose_ref=purpose_ref, source_as_of=str(source_as_of), split_spec=spec.to_dict(),
        review_status=review_status, samples=tuple(rows),
        sample_digests=tuple(str(row["sample_digest"]) for row in rows),
        exclusions=tuple(exclusion.to_dict() for exclusion in exclusions),
        exclusion_stats=exclusion_stats, counts=counts, completeness=completeness)


def render_samples(manifest: DatasetManifest) -> bytes:
    """Deterministic jsonl body of one dataset version."""
    return b"".join(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8") + b"\n"
        for row in manifest.samples)


def artifact_digest(manifest: DatasetManifest) -> str:
    return hashlib.sha256(render_samples(manifest)).hexdigest()


def manifest_spec(manifest: DatasetManifest) -> SplitSpec:
    """Reconstruct the frozen split spec of an existing manifest revision."""
    data = dict(manifest.split_spec)
    return SplitSpec(group_by=str(data.get("group_by", "project_task_lineage")),
                     seed=str(data.get("seed", "1")),
                     train_percent=int(data.get("train_percent", 80)),
                     eval_percent=int(data.get("eval_percent", 10)),
                     test_percent=int(data.get("test_percent", 10)))


class FileSystemSink:
    """Publishes one dataset version; a published version is never overwritten."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def directory(self, manifest: DatasetManifest, *, version: str) -> Path:
        for value in (manifest.dataset_id, str(version)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
                raise ValueError("dataset and version must be safe path segments")
        root = self.root.resolve()
        directory = (root / manifest.dataset_id / str(version)).resolve()
        if not directory.is_relative_to(root):
            raise ValueError("dataset output leaves its sink")
        return directory

    def inspect(self, manifest: DatasetManifest, *, version: str) -> tuple[str, tuple[str, ...]]:
        """Prove a complete effect from exact bytes; absence alone stays unknown."""
        directory = self.directory(manifest, version=version)
        files = (directory / "samples.jsonl", directory / "manifest.json")
        try:
            if any(path.is_symlink() or not path.is_file() for path in files):
                return "unknown", ()
            if files[0].read_bytes() != render_samples(manifest):
                return "unknown", ()
            if json.loads(files[1].read_text(encoding="utf-8")) != manifest.to_dict():
                return "unknown", ()
        except (OSError, ValueError):
            return "unknown", ()
        return "applied", tuple(str(path) for path in files)

    def write(self, manifest: DatasetManifest, *, version: str) -> tuple[str, ...]:
        directory = self.directory(manifest, version=version)
        if directory.exists():
            raise FileExistsError(
                f"dataset {manifest.dataset_id} version {version} already exists; "
                "a published dataset is never overwritten")
        payload = render_samples(manifest)
        directory.mkdir(parents=True, exist_ok=False)
        samples_path = directory / "samples.jsonl"
        manifest_path = directory / "manifest.json"
        with samples_path.open("xb") as stream:
            stream.write(payload)
        with manifest_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest.to_dict(), sort_keys=True,
                                    ensure_ascii=False, indent=2))
        return (str(samples_path), str(manifest_path))


__all__ = [
    "CorpusExportError", "FileSystemSink", "artifact_digest", "build_manifest",
    "manifest_spec", "redact", "render_samples",
]
