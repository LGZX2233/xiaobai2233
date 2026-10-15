"""ScoreEngine tests (AC34 + task acceptance #3): separate use kinds, duplicate
suppression, traceable rollback/correction, versioned decay."""
from __future__ import annotations

from project_kernel.contracts.dto import ObjectRef
from project_kernel.knowledge import (
    OutcomeEvent,
    ScoreEngine,
    ScoringConfig,
    UseEvent,
)

_K = ObjectRef("proj-a", "knowledge", "k-1", "rev-1")


def _use(key: str, kind: str = "adopted") -> UseEvent:
    return UseEvent(source_use_key=key, use_kind=kind, knowledge_ref=_K,
                    project_id="proj-a")


def _outcome(key: str, kind: str = "success", use_key: str = "") -> OutcomeEvent:
    return OutcomeEvent(source_outcome_key=key, outcome_kind=kind,
                        project_id="proj-a", use_source_key=use_key)


def _engine(decay_lambda: float = 0.0) -> ScoreEngine:
    return ScoreEngine(ScoringConfig.exponential(decay_lambda=decay_lambda))


# --- use kinds are separate ---------------------------------------------------

def test_only_adopted_use_contributes():
    score = _engine().score(
        [_use("use-1", "retrieved"), _use("use-2", "injected"),
         _use("use-3", "adopted")], [])
    assert score.score == 1.0
    kinds = {d.kind for d in score.trace}
    assert kinds == {"use:adopted"}


def test_success_and_failure_outcomes_combine():
    score = _engine().score([], [_outcome("o-1", "success"), _outcome("o-2", "failure")])
    assert score.score == 0.5


# --- duplicate suppression ----------------------------------------------------

def test_duplicate_use_does_not_double_count():
    score = _engine().score([_use("use-1"), _use("use-1")], [])
    assert score.score == 1.0
    assert score.causal_refs == ("use-1",)


def test_duplicate_outcome_does_not_double_count():
    score = _engine().score([], [_outcome("o-1", "success"), _outcome("o-1", "success")])
    assert score.score == 1.0
    assert score.causal_refs == ("o-1",)


# --- rollback / correction traceability ---------------------------------------

def test_rollback_is_traceable_and_reduces_linked_use():
    score = _engine().score(
        [_use("use-1", "adopted")],
        [_outcome("o-1", "rollback", use_key="use-1")])
    assert score.score == 0.0
    reasons = [d.reason for d in score.trace]
    assert any("rollback" in r and "use-1" in r for r in reasons)


def test_correction_is_traceable():
    score = _engine().score(
        [_use("use-1", "adopted")],
        [_outcome("o-1", "correction", use_key="use-1")])
    assert score.score == 0.0
    assert "o-1" in score.causal_refs


def test_rollback_without_linked_use_still_recorded():
    score = _engine().score(
        [_use("use-1", "adopted")],
        [_outcome("o-1", "rollback", use_key="use-2")])
    # rollback does not retroactively cancel an unrelated use
    assert score.score == 0.0


# --- versioned decay ----------------------------------------------------------

def test_decay_version_changes_score():
    plain = _engine(0.0).score([_use("use-1"), _use("use-2")], [])
    decayed = _engine(0.5).score([_use("use-1"), _use("use-2")], [])
    assert plain.score == 2.0
    assert decayed.score < plain.score
    assert plain.score_version == decayed.score_version == "v1"


def test_score_is_deterministic_and_idempotent():
    events_u = [_use("use-1"), _use("use-2")]
    events_o = [_outcome("o-1"), _outcome("o-2", "failure")]
    a = _engine().score(events_u, events_o)
    b = _engine().score(events_u, events_o)
    assert a.score == b.score
    assert a.to_dict() == b.to_dict()
