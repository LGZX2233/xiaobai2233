"""Migration runner and checksum verification (P01 owner)."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ...contracts.errors import KernelError, migration_checksum_mismatch, schema_incompatible

SCHEMA_VERSION = "1.0.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migration ("
        " migration_id TEXT PRIMARY KEY, checksum TEXT NOT NULL,"
        " applied_at TEXT NOT NULL, schema_version TEXT NOT NULL)"
    )


def _applied(conn: sqlite3.Connection) -> dict[str, str]:
    return {row[0]: row[1] for row in conn.execute("SELECT migration_id, checksum FROM schema_migration")}


def apply_migrations(conn: sqlite3.Connection, migrations: list[tuple[str, str]]) -> None:
    """Apply pending migrations in order; refuse to run if an applied migration's
    checksum differs from the frozen one."""
    _ensure_migration_table(conn)
    applied = _applied(conn)
    for mid, sql in migrations:
        checksum = _checksum(sql)
        if mid in applied:
            if applied[mid] != checksum:
                raise KernelError(migration_checksum_mismatch(
                    f"migration {mid} checksum mismatch: expected {checksum[:12]}…"))
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migration (migration_id, checksum, applied_at, schema_version)"
            " VALUES (?, ?, ?, ?)",
            (mid, checksum, _utc_now(), SCHEMA_VERSION),
        )
        conn.commit()


def verify_migrations(conn: sqlite3.Connection, migrations: list[tuple[str, str]]) -> None:
    """Read-only verification: every frozen migration applied with matching checksum."""
    _ensure_migration_table(conn)
    applied = _applied(conn)
    for mid, sql in migrations:
        checksum = _checksum(sql)
        if mid not in applied:
            raise KernelError(schema_incompatible(f"migration {mid} not applied"))
        if applied[mid] != checksum:
            raise KernelError(migration_checksum_mismatch(f"migration {mid} checksum mismatch"))
