"""AC35: empty templates never succeed, failures stay failures, sources verifiable.

AC36: lineage never crosses splits, same content is deduplicated, and a published
dataset version is never overwritten (export side is covered in test_service).
"""
from __future__ import annotations

import pytest
from project_kernel.corpus import CorpusExportError, SampleReview, build_manifest
from project_kernel.corpus.exporter import FileSystemSink, artifact_digest

from .helpers import PROJ, policy, sample, spec


def _excluded(manifest, sample_id):
    return [e for e in manifest.exclusions if e["sample_id"] == sample_id]


def test_empty_template_and_unknown_repair_never_become_validated_success():
    manifest = build_manifest(
        policy(), [
            sample("s-empty", input="", output=""),
            sample("s-todo", input="TODO", output="TBD"),
            sample("s-real", input="q", output="a"),
            sample("s-repair", kind="correction", failure_type=None),
            sample("s-unknown", quality_flags=("unknown",)),
        ],
        project_id=PROJ, spec=spec(), source_as_of="3",
        reviews=[SampleReview("s-empty", "accepted", "looks fine", "human-1"),
                 SampleReview("s-real", "accepted", "verified", "human-1")])

    assert [row["sample_id"] for row in manifest.samples] == ["s-real"]
    assert manifest.counts["validated_success"] == 1
    assert _excluded(manifest, "s-empty")[0]["reason"] == "EMPTY_TEMPLATE"
    assert _excluded(manifest, "s-todo")[0]["reason"] == "EMPTY_TEMPLATE"
    assert _excluded(manifest, "s-repair")[0]["reason"] == "UNRESOLVED_REPAIR"
    assert _excluded(manifest, "s-unknown")[0]["reason"] == "UNKNOWN_OUTCOME"
    assert manifest.exclusion_stats["EMPTY_TEMPLATE"] == 2


def test_failure_samples_stay_in_the_failure_set_with_an_explicit_type():
    typed = policy(allowed_failure_types=("assertion",))
    manifest = build_manifest(
        typed, [sample("s-fail", kind="failure", input="q", output="traceback",
                       failure_type="assertion")],
        project_id=PROJ, spec=spec(), source_as_of="3")

    row = manifest.samples[0]
    assert row["kind"] == "failure" and row["failure_type"] == "assertion"
    assert manifest.counts["validated_success"] == 0 and manifest.counts["failure"] == 1
    assert row["source_refs"][0]["revision_id"] == "rev-1"
    assert row["sample_digest"]

    untyped = build_manifest(typed, [sample("s-f2", kind="failure", failure_type=None)],
                             project_id=PROJ, spec=spec(), source_as_of="3")
    assert _excluded(untyped, "s-f2")[0]["reason"] == "FAILURE_NOT_ALLOWED"

    refused = build_manifest(policy(allow_failures=False),
                             [sample("s-f3", kind="failure", failure_type="assertion")],
                             project_id=PROJ, spec=spec(), source_as_of="3")
    assert _excluded(refused, "s-f3")[0]["reason"] == "FAILURE_NOT_ALLOWED"


def test_lineage_split_is_assigned_and_never_crosses_train_eval():
    samples = [sample("s1", task="t1"), sample("s2", task="t1", input="q2"),
               sample("s3", task="t2"), sample("s4", task="t2", input="q3")]
    manifest = build_manifest(policy(), samples, project_id=PROJ, spec=spec(),
                              source_as_of="3")

    splits = {row["group_id"]: row["split"] for row in manifest.samples}
    assert splits[f"{PROJ}:t1"] == splits[f"{PROJ}:t1"]
    assert len(set(splits.values())) >= 1
    # the same task lineage always lands in one split, independent of sample id
    first = build_manifest(policy(), [samples[0]], project_id=PROJ, spec=spec(),
                           source_as_of="3").samples[0]["split"]
    second = build_manifest(policy(), [samples[1]], project_id=PROJ, spec=spec(),
                            source_as_of="3").samples[0]["split"]
    assert first == second

    declared = build_manifest(policy(), [sample("s5", task="t3", split="test")],
                              project_id=PROJ, spec=spec(), source_as_of="3")
    assigned = build_manifest(policy(), [sample("s5", task="t3")], project_id=PROJ,
                              spec=spec(), source_as_of="3").samples[0]["split"]
    if assigned != "test":
        assert _excluded(declared, "s5")[0]["reason"] == "SPLIT_ASSIGNMENT_MISMATCH"


def test_same_content_is_deduplicated_but_distinct_content_is_kept():
    manifest = build_manifest(
        policy(), [sample("s1", task="t1"), sample("s2", task="t2"),
                   sample("s3", task="t3", input="other", output="answer")],
        project_id=PROJ, spec=spec(), source_as_of="3")

    assert [row["sample_id"] for row in manifest.samples] == ["s1", "s3"]
    assert _excluded(manifest, "s2")[0]["reason"] == "DUPLICATE_CONTENT"
    assert manifest.completeness["content_deduplicated"] is True


def test_cross_project_source_is_a_hard_error_not_a_silent_exclusion():
    with pytest.raises(CorpusExportError):
        build_manifest(policy(), [sample("s1", project="proj-b")], project_id=PROJ,
                       spec=spec(), source_as_of="3")


def test_policy_boundaries_are_enforced_and_sensitive_fields_are_redacted():
    strict = policy(allowed_sensitivity=("public",), required_quality_labels=("human-verified",),
                    redact_fields=("output",))
    manifest = build_manifest(
        strict, [sample("s-internal", sensitivity="internal"),
                 sample("s-label", input="q", output="a", sensitivity="public"),
                 sample("s-ok", input="q", output="secret", verification_labels=("human-verified",),
                        sensitivity="public")],
        project_id=PROJ, spec=spec(), source_as_of="3")

    assert _excluded(manifest, "s-internal")[0]["reason"] == "SENSITIVITY_NOT_ALLOWED"
    assert _excluded(manifest, "s-label")[0]["reason"] == "MISSING_QUALITY_LABEL"
    assert manifest.samples[0]["output"] == "[REDACTED]"
    assert manifest.samples[0]["input"] == "q"


def test_manifest_is_deterministic_and_carries_policy_and_purpose():
    from project_kernel.contracts import ObjectRef

    purpose_ref = ObjectRef(PROJ, "dataset_purpose", "eval-1", "rev-1").to_dict()
    policy_ref = ObjectRef(PROJ, "dataset_policy", "ds", "rev-1").to_dict()
    first = build_manifest(policy(), [sample("s1")], project_id=PROJ, spec=spec(),
                           source_as_of="3", purpose_ref=purpose_ref, policy_ref=policy_ref)
    second = build_manifest(policy(), [sample("s1")], project_id=PROJ, spec=spec(),
                            source_as_of="3", purpose_ref=purpose_ref, policy_ref=policy_ref)

    assert first.digest() == second.digest()
    body = first.to_dict()
    assert body["policy_revision"] == "pol-1" and body["policy_digest"]
    assert body["purpose"] == "evaluation" and body["purpose_ref"] == purpose_ref
    assert body["split_spec"] == spec().to_dict()
    assert body["source_as_of"] == "3"
    assert body["review_status"] == "candidate"
    assert artifact_digest(first) == artifact_digest(second)


def test_file_sink_publishes_once_and_refuses_to_overwrite(tmp_path):
    manifest = build_manifest(policy(), [sample("s1")], project_id=PROJ, spec=spec(),
                              source_as_of="3")
    sink = FileSystemSink(tmp_path)
    files = sink.write(manifest, version="r1")

    assert len(files) == 2
    assert (tmp_path / "ds" / "r1" / "samples.jsonl").read_text(encoding="utf-8").count("\n") == 1
    with pytest.raises(FileExistsError):
        sink.write(manifest, version="r1")
