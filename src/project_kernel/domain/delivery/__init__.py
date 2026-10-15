"""P04-owned delivery domain (verification, approval, delivery).

Pure state/reasoning helpers consumed by ``application/delivery``: effect
classification for reconciliation, archive completeness, and the decisive-input
projection used to decide whether a frozen snapshot is still eligible.
"""
from .archive import archive_overall, sink_is_terminal
from .effect import (
    classify_effect,
    delivery_state_for_effect,
    is_effect_final,
    reconcile_requires_terminal_evidence,
)
from .eligibility import (
    NON_DECISIVE_KEYS,
    decisive_projection,
    iter_refs,
    ref_key,
)

__all__ = [
    "archive_overall",
    "sink_is_terminal",
    "classify_effect",
    "delivery_state_for_effect",
    "is_effect_final",
    "reconcile_requires_terminal_evidence",
    "NON_DECISIVE_KEYS",
    "decisive_projection",
    "iter_refs",
    "ref_key",
]
