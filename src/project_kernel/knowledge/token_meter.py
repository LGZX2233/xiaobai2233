"""Token metering port (P08 deliverable #1).

The offline meter is a deterministic estimator only; unknown metering must be
marked `estimated` and is never presented as an exact count (design 05 §1: an
unknown meter must not pretend precision, keep a conservative margin). Exact
metering is the responsibility of a real DSH metering provider wired in by P11;
no paid model is called here.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TokenMeterPort(Protocol):
    def estimate_tokens(self, text: str) -> int: ...
    def is_exact(self) -> bool: ...


class DeterministicTokenMeter:
    """Offline, deterministic token estimator.

    Counts whitespace-delimited word tokens with CJK runs treated per-glyph.
    It is intentionally conservative (never under-counts relative to a
    word-piece tokenizer in the common case) and always reports `estimated`.
    """

    def __init__(self, fallback_token_count: int = 1) -> None:
        self.fallback_token_count = fallback_token_count

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        words = text.split()
        # CJK/ideographic runs are counted per character, not per whitespace word.
        total = 0
        for word in words:
            cjk = sum(1 for ch in word if "\u4e00" <= ch <= "\u9fff")
            ascii_words = max(len([w for w in _split_ascii(word)]), 1)
            total += max(ascii_words, cjk)
        return max(total, self.fallback_token_count)

    def is_exact(self) -> bool:
        return False


def _split_ascii(word: str) -> list[str]:
    """Split an ASCII word on punctuation to avoid over-counting markup."""
    out: list[str] = []
    current: list[str] = []
    for ch in word:
        if ch.isalnum() or ch in "_-'":
            current.append(ch)
        else:
            if current:
                out.append("".join(current))
                current = []
    if current:
        out.append("".join(current))
    return out or [word]


class ExactTokenMeter:
    """Placeholder for a real metering provider (DSH) wired in by P11.

    Never constructed with a fabricated count: it must be supplied a callable
    that produced a real token count, otherwise estimation is used.
    """

    def __init__(self, counter: Any) -> None:
        self._counter = counter

    def estimate_tokens(self, text: str) -> int:
        return int(self._counter(text))

    def is_exact(self) -> bool:
        return True
