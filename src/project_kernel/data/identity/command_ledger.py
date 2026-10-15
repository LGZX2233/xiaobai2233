"""Durable idempotency ledger for identity RPC commands."""
from __future__ import annotations

import json
import sqlite3

IDENTITY_COMMAND_RECEIPT_DDL = """
CREATE TABLE IF NOT EXISTS identity_command_receipt (
    principal_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    command_kind TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    command_id TEXT NOT NULL,
    status TEXT NOT NULL,
    request_id TEXT,
    commit_seq INTEGER,
    receipt_json TEXT,
    result_json TEXT,
    PRIMARY KEY (principal_id, idempotency_key)
) WITHOUT ROWID;
"""

IDENTITY_COMMAND_MIGRATION = ("0003_identity_command_receipt", IDENTITY_COMMAND_RECEIPT_DDL)


class IdentityCommandLedger:
    """Persist identity command receipts and pending provision request IDs."""

    def __init__(self, conn: sqlite3.Connection, store_id: str):
        self.conn = conn
        self.store_id = store_id

    def next_commit_seq(self) -> int:
        row = self.conn.execute(
            "SELECT commit_seq FROM identity_meta WHERE store_id=?", (self.store_id,)
        ).fetchone()
        return int(row[0]) + 1 if row else 1

    def save_commit_seq(self, commit_seq: int) -> None:
        self.conn.execute(
            "INSERT INTO identity_meta (store_id, commit_seq) VALUES (?,?) "
            "ON CONFLICT(store_id) DO UPDATE SET commit_seq=excluded.commit_seq",
            (self.store_id, commit_seq),
        )

    @staticmethod
    def decode(row) -> dict | None:
        if row is None:
            return None
        return {"command_kind": row[0], "input_hash": row[1], "command_id": row[2],
                "status": row[3], "request_id": row[4], "commit_seq": row[5],
                "receipt": json.loads(row[6]) if row[6] else None,
                "result": json.loads(row[7]) if row[7] else None}

    def lookup(self, principal_id: str, idempotency_key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT command_kind,input_hash,command_id,status,request_id,commit_seq,"
            "receipt_json,result_json FROM identity_command_receipt "
            "WHERE principal_id=? AND idempotency_key=?", (principal_id, idempotency_key)
        ).fetchone()
        return self.decode(row)
