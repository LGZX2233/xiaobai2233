"""Pure EffectReceipt classification for delivery reconciliation (P04).

Reconciliation only ever *queries* the real target; it never replays an
external write. A missing target on its own is never proof that no effect
happened, so it stays `absent_pending`/`unknown` and keeps blocking. Only a
terminal execution (provider reported a final outcome and cleaned up) or an
explicit external fence can prove `absent_final`.
"""
from __future__ import annotations

from ...contracts import EffectStatus

#: preconditions that mean "a new worker must not take over automatically"
APPLYING = "applying"
CLAIMED = "claimed"


def classify_effect(*, target_present: bool, digest_matches: bool | None,
                    execution_terminal: bool = False, external_fence: bool = False,
                    effect_query_failed: bool = False) -> str:
    """Map a real effect query into an EffectReceipt status.

    - target present + matching pinned digest -> ``applied`` (idempotent re-read)
    - target present + different/unknown content -> ``unknown`` (never overwrite)
    - target absent + terminal execution or external fence -> ``absent_final``
    - target absent otherwise -> ``absent_pending`` (still in flight / unknown)
    """
    if effect_query_failed:
        return EffectStatus.UNKNOWN.value
    if target_present:
        if digest_matches is True:
            return EffectStatus.APPLIED.value
        return EffectStatus.UNKNOWN.value
    if execution_terminal or external_fence:
        return EffectStatus.ABSENT_FINAL.value
    return EffectStatus.ABSENT_PENDING.value


def is_effect_final(status: str) -> bool:
    """Only applied or provably-no-effect may release a delivery blocker."""
    return status in (EffectStatus.APPLIED.value, EffectStatus.ABSENT_FINAL.value)


def delivery_state_for_effect(status: str) -> str:
    """EffectReceipt -> Delivery state. absent_pending/unknown never settle."""
    if status == EffectStatus.APPLIED.value:
        return "applied"
    if status == EffectStatus.ABSENT_FINAL.value:
        return "failed"
    return "unknown"


def reconcile_requires_terminal_evidence(status: str, *, execution_terminal: bool,
                                         fence_evidence_ref: object | None) -> bool:
    """absent_final is only legitimate with execution_terminal=true *and* a
    terminal/fence basis; a bare "target file is missing right now" is not."""
    if status != EffectStatus.ABSENT_FINAL.value:
        return False
    return bool(execution_terminal) or fence_evidence_ref is not None
