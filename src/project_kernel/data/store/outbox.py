"""Outbox: at-least-once claim/ack with lease tokens.

A side effect is performed *outside* the short transaction between claim and
ack; a worker crash re-delivers. acks carry the lease token: a stale token only
records an audit and can never overwrite a newer owner.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from ...contracts.errors import KernelError, temporary_unavailable


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Outbox:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def enqueue(self, consumer: str, effect_id: str, effect_kind: str,
                payload_ref: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO outbox (consumer, effect_id, effect_kind, payload_ref, state)"
            " VALUES (?,?,?,?, 'pending')",
            (consumer, effect_id, effect_kind, payload_ref),
        )
        if cur.rowcount == 0:
            row = self.conn.execute(
                "SELECT outbox_id FROM outbox WHERE consumer=? AND effect_id=? AND effect_kind=?",
                (consumer, effect_id, effect_kind)).fetchone()
            return int(row[0])
        return int(cur.lastrowid)

    def claim(self, consumer: str, effect_id: str, effect_kind: str,
              lease_seconds: int = 60) -> dict[str, Any]:
        token = _new_token()
        until = _utc_iso(datetime.now(timezone.utc) + timedelta(seconds=lease_seconds))
        row = self.conn.execute(
            "SELECT outbox_id, state, lease_until FROM outbox"
            " WHERE consumer=? AND effect_id=? AND effect_kind=?",
            (consumer, effect_id, effect_kind)).fetchone()
        if row is None:
            raise KernelError(temporary_unavailable(f"no outbox effect {effect_id}"))
        outbox_id, state, lease_until = row[0], row[1], row[2]
        if state == "acked":
            return {"outbox_id": outbox_id, "already_acked": True}
        if state == "leased" and lease_until is not None and lease_until > _utc_now():
            raise KernelError(temporary_unavailable(f"effect {effect_id} is leased"))
        self.conn.execute(
            "UPDATE outbox SET state='leased', lease_token=?, lease_until=?, attempts=attempts+1"
            " WHERE outbox_id=?",
            (token, until, outbox_id),
        )
        return {"outbox_id": outbox_id, "lease_token": token, "lease_until": until}

    def ack(self, outbox_id: int, lease_token: str) -> bool:
        cur = self.conn.execute(
            "UPDATE outbox SET state='acked', lease_token=NULL, lease_until=NULL"
            " WHERE outbox_id=? AND lease_token=?",
            (outbox_id, lease_token),
        )
        return cur.rowcount == 1

    def fail(self, outbox_id: int, lease_token: str, error: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET state='failed', error=? WHERE outbox_id=? AND lease_token=?",
            (error, outbox_id, lease_token),
        )


def _new_token() -> str:
    import secrets
    return secrets.token_hex(16)


def _utc_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
