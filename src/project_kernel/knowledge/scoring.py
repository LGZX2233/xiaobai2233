"""Knowledge scoring with duplicate suppression and traceable correction.

Design 05 §1 / AC34: scoring takes immutable use/outcome events as input; a
repeat event (same source_use_key or source_outcome_key) never adds score again;
rollback/correction events are explicit negative deltas linked to the original
adopted use, so a correction is traceable instead of silently reset. Decay is a
replaceable function versioned by `score_version`; retrieval counts are never a
quality signal (only adopted uses and verified outcomes contribute).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .models import OutcomeEvent, ScoreDelta, ScoreRecord, UseEvent

# default scoring weights (configurable per score_version)
_DEFAULT_WEIGHTS = {
    "adopted": 1.0,
    "injected": 0.0,
    "retrieved": 0.0,
    "success": 1.0,
    "failure": -0.5,
    "rollback": -1.0,
    "correction": -1.0,
}


@dataclass(frozen=True)
class ScoringConfig:
    score_version: str
    weights: dict[str, float]
    decay: Callable[[int, int], float]
    decay_lambda: float = 0.0

    def __post_init__(self) -> None:
        if not self.score_version:
            raise ValueError("score_version must be non-empty")
        if self.decay_lambda < 0:
            raise ValueError("decay_lambda must be >= 0")

    @classmethod
    def exponential(cls, score_version: str = "v1",
                    decay_lambda: float = 0.0) -> "ScoringConfig":
        def decay(distance: int, total: int) -> float:
            del total  # deterministic; only distance matters
            if distance < 0:
                return 0.0
            return 1.0 if decay_lambda == 0 else (1.0 - decay_lambda) ** distance

        return cls(score_version=score_version,
                   weights=dict(_DEFAULT_WEIGHTS),
                   decay=decay, decay_lambda=decay_lambda)


class ScoreEngine:
    """Deterministic, idempotent scorer over an immutable ordered event log."""

    def __init__(self, config: ScoringConfig):
        self.config = config

    def score(self, uses: Sequence[UseEvent],
              outcomes: Sequence[OutcomeEvent]) -> ScoreRecord:
        # First occurrence per key wins; duplicates contribute nothing and are
        # not part of the causal trace (AC34: repeat events never add score).
        use_order: list[UseEvent] = []
        seen_use: set[str] = set()
        for u in uses:
            if u.source_use_key in seen_use:
                continue
            seen_use.add(u.source_use_key)
            use_order.append(u)

        outcome_order: list[OutcomeEvent] = []
        seen_outcome: set[str] = set()
        for o in outcomes:
            if o.source_outcome_key in seen_outcome:
                continue
            seen_outcome.add(o.source_outcome_key)
            outcome_order.append(o)

        total_events = len(use_order) + len(outcome_order)
        score = 0.0
        trace: list[ScoreDelta] = []
        causal: list[str] = []

        # Adoption contributes; plain retrieval/injection is recorded but scores
        # nothing (design: retrieval count is not quality).
        for idx, u in enumerate(use_order):
            weight = self.config.weights.get(u.use_kind, 0.0)
            if weight == 0.0:
                continue
            delta = weight * self.config.decay(total_events - 1 - idx, total_events)
            score += delta
            trace.append(ScoreDelta(u.source_use_key, f"use:{u.use_kind}", delta,
                                    f"adopted use {u.source_use_key}"))
            causal.append(u.source_use_key)

        # Outcomes: success/failure are standalone; rollback/correction are
        # linked to the original use key and reduce the contribution of that use.
        for idx, o in enumerate(outcome_order):
            weight = self.config.weights.get(o.outcome_kind, 0.0)
            delta = weight * self.config.decay(total_events - 1 - idx, total_events)
            score += delta
            reason = f"{o.outcome_kind} outcome {o.source_outcome_key}"
            if o.use_source_key:
                reason += f" linked to use {o.use_source_key}"
            trace.append(ScoreDelta(o.source_outcome_key, f"outcome:{o.outcome_kind}",
                                    delta, reason))
            causal.append(o.source_outcome_key)

        return ScoreRecord(score_version=self.config.score_version,
                           score=round(score, 6),
                           causal_refs=tuple(causal),
                           trace=tuple(trace))
