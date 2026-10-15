"""Read-only legacy source manifest: per-file hash, schema and row counts.

The manifest is the source-consistent evidence that the legacy source was read
without modification. It never writes to the source: it only reads file bytes
and (optionally) opens the legacy SQLite in read-only mode.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...contracts.digest import sha256_digest, sha256_file

MANIFEST_SCHEMA_VERSION = "1.0.0"
LEGACY_DB_NAME = "legacy.sqlite"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class FileEntry:
    rel_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"rel_path": self.rel_path, "sha256": self.sha256,
                "size_bytes": str(self.size_bytes)}


@dataclass(frozen=True)
class TableCount:
    table: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "count": str(self.count)}


@dataclass(frozen=True)
class LegacySourceManifest:
    source_store_id: str
    source_root: str
    files: tuple[FileEntry, ...]
    tables: tuple[TableCount, ...]
    created_at: str

    def body(self) -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "canonicalization": "rfc8785",
            "source_store_id": self.source_store_id,
            "source_root": self.source_root,
            "files": [f.to_dict() for f in self.files],
            "tables": [t.to_dict() for t in self.tables],
        }

    @property
    def digest(self) -> str:
        """JCS(SHA-256) over the canonical manifest body (no shell fields)."""
        return sha256_digest(self.body())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "digest": self.digest, "created_at": self.created_at}

    def file_hash(self, rel_path: str) -> str | None:
        for f in self.files:
            if f.rel_path == rel_path:
                return f.sha256
        return None


def _count_table_rows(conn: sqlite3.Connection, table: str) -> int:
    # Table names come from sqlite_master (trusted local read-only DB); the
    # quoted identifier is still validated below to avoid malformed names.
    if not table.replace("_", "").isalnum():
        return 0
    row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
    return int(row[0]) if row else 0


def _read_tables(source_root: Path) -> tuple[TableCount, ...]:
    db = source_root / LEGACY_DB_NAME
    if not db.exists():
        return ()
    uri = f"file:{db.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    try:
        conn.execute("PRAGMA query_only = ON")
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        ).fetchall()
        return tuple(TableCount(table=r[0], count=_count_table_rows(conn, r[0])) for r in rows)
    finally:
        conn.close()


def build_source_manifest(source_root: Path, source_store_id: str) -> LegacySourceManifest:
    """Build a read-only manifest over every file under *source_root*.

    All files are hashed (sorted relative paths) and, when ``legacy.sqlite`` is
    present, the table list and per-table row counts are recorded. No file or
    database in the source is ever opened for writing.
    """
    source_root = Path(source_root)
    files: list[FileEntry] = []
    for path in sorted(p for p in source_root.rglob("*") if p.is_file()):
        rel = path.relative_to(source_root).as_posix()
        files.append(FileEntry(rel_path=rel, sha256=sha256_file(path),
                               size_bytes=path.stat().st_size))
    return LegacySourceManifest(
        source_store_id=source_store_id,
        source_root=str(source_root),
        files=tuple(files),
        tables=_read_tables(source_root),
        created_at=_utc_now(),
    )
