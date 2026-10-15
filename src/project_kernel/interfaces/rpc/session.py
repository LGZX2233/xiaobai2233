"""Session-scoped protocol guards: in-flight limit and receipt replay.

Both are *transport* concerns, not business authority:

* ``InFlightLimiter`` bounds concurrent in-flight requests. It is non-blocking —
  exceeding the limit returns a retryable ``TEMPORARY_UNAVAILABLE`` instead of
  queueing, so a stalled handler can never deadlock the reader loop.
* ``ReceiptLedger`` caches receipts the *server itself* returned, keyed by
  (principal, idempotency_key). It replays the original receipt for a
  same-key/same-hash retry, refuses a same-key/different-hash retry with
  ``IDEMPOTENCY_CONFLICT``, and lets a client that lost the connection re-read
  its receipt with the original key. It never manufactures a receipt and never
  advances business state; the store stays authoritative for durability.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Mapping

from ...contracts.errors import (
    KernelError,
    idempotency_conflict,
    temporary_unavailable,
)

REPLAY_NEW = "new"
REPLAY_HIT = "replay"
REPLAY_CONFLICT = "conflict"


class InFlightLimiter:
    """Bounded, non-blocking in-flight counter."""

    def __init__(self, max_inflight: int) -> None:
        if max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        self.max_inflight = int(max_inflight)
        self._lock = threading.Lock()
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def try_acquire(self) -> None:
        with self._lock:
            if self._in_flight >= self.max_inflight:
                raise KernelError(temporary_unavailable(
                    f"in-flight limit of {self.max_inflight} reached; retry shortly"))
            self._in_flight += 1

    def release(self) -> None:
        with self._lock:
            if self._in_flight > 0:
                self._in_flight -= 1

    def __enter__(self) -> "InFlightLimiter":
        self.try_acquire()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.release()


@dataclass(frozen=True)
class LedgerEntry:
    input_hash: str
    receipt: Mapping[str, Any]


class ReceiptLedger:
    """Bounded (principal, key) -> receipt cache for retry/reconnect."""

    def __init__(self, *, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self.max_entries = int(max_entries)
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], LedgerEntry] = {}
        self._order: list[tuple[str, str]] = []

    def lookup(self, principal_id: str, idempotency_key: str) -> Mapping[str, Any] | None:
        with self._lock:
            entry = self._entries.get((principal_id, idempotency_key))
        return entry.receipt if entry is not None else None

    def begin(self, principal_id: str, idempotency_key: str,
              input_hash: str) -> tuple[str, Mapping[str, Any] | None]:
        with self._lock:
            entry = self._entries.get((principal_id, idempotency_key))
            if entry is None:
                return REPLAY_NEW, None
            if entry.input_hash == input_hash:
                return REPLAY_HIT, entry.receipt
            return REPLAY_CONFLICT, entry.receipt

    def record(self, principal_id: str, idempotency_key: str, input_hash: str,
               receipt: Mapping[str, Any] | None) -> None:
        """Remember a receipt the server just returned (never a synthetic one)."""
        if not isinstance(receipt, Mapping) or "status" not in receipt:
            # Only a real CommandReceipt shape is replayable.
            return
        key = (principal_id, idempotency_key)
        with self._lock:
            if key in self._entries:
                self._order.remove(key)
            self._entries[key] = LedgerEntry(input_hash=input_hash, receipt=dict(receipt))
            self._order.append(key)
            while len(self._order) > self.max_entries:
                self._entries.pop(self._order.pop(0), None)

    def forget(self, principal_id: str, idempotency_key: str) -> None:
        key = (principal_id, idempotency_key)
        with self._lock:
            if self._entries.pop(key, None) is not None:
                self._order.remove(key)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
