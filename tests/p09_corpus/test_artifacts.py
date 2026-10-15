"""Test-artifact classification, script promotion and tombstone rules (P09)."""
from __future__ import annotations

from project_kernel.contracts import ObjectRef
from project_kernel.corpus import (
    CorpusArtifact,
    ScriptArtifact,
    ScriptTestResult,
    corpus_eligibility,
    is_empty_template,
    tombstone_for,
)

from .helpers import PROJ, sample


def _ref():
    return ObjectRef(PROJ, "artifact", "art-1", "rev-1")


def test_only_provenance_carrying_fixtures_become_corpus_candidates():
    golden = CorpusArtifact("a1", "golden", "a" * 64, (_ref(),), {"purpose": "vector"})
    temp = CorpusArtifact("a2", "temp", "b" * 64, (_ref(),), {"purpose": "scratch"},
                          collected_from="pytest tmp_path")
    no_provenance = CorpusArtifact("a3", "failure_bundle", "c" * 64, ())
    report = CorpusArtifact("a4", "reports", "d" * 64, (_ref(),), {})

    assert corpus_eligibility(golden) == (True, "")
    eligible, reason = corpus_eligibility(temp)
    assert (eligible, "never corpus" in reason) == (False, True)
    assert corpus_eligibility(no_provenance)[0] is False
    assert corpus_eligibility(report)[0] is False
    assert corpus_eligibility(
        CorpusArtifact("a5", "reports", "e" * 64, (_ref(),), {"purpose": "release"}))[0] is True


def test_script_promotion_needs_real_passing_test_evidence():
    base = {"script_id": "s-1", "purpose": "replay", "source_attempt_ref": _ref(),
            "source_digest": "a" * 64, "input_schema_ref": "in", "output_schema_ref": "out",
            "runtime_env": {"python": "3.12"}, "permissions": ("exec",)}

    assert ScriptArtifact(**base).promotion_status() == "not_eligible"
    failed = ScriptArtifact(**base, test_results=(ScriptTestResult("t", "failed", "d" * 64),))
    assert failed.promotion_status() == "not_eligible"
    unproven = ScriptArtifact(**base, test_results=(ScriptTestResult("t", "passed", ""),))
    assert unproven.promotion_status() == "not_eligible"
    passed = ScriptArtifact(**base, test_results=(ScriptTestResult("t", "passed", "d" * 64),))
    assert passed.promotion_status() == "candidate"


def test_tombstone_keeps_the_hash_of_deleted_content():
    tombstone = tombstone_for(sample("s1"), "retention policy")

    assert tombstone["state"] == "deleted"
    assert tombstone["digest"] and tombstone["object_id"] == "s1"
    assert len(tombstone["digest"]) == 64


def test_placeholder_detection_covers_empty_and_template_values():
    assert is_empty_template(None) and is_empty_template("") and is_empty_template("TODO")
    assert is_empty_template({}) and is_empty_template([])
    assert not is_empty_template("real answer")
    assert not is_empty_template({"output": "real"})
