"""Read-only legacy source reader plus the synthetic sanitized sample builder.

A legacy source directory contains either::

  legacy.sqlite   -- legacy SQLite database (opened read-only), or
  records.jsonl   -- one JSON object per line (sanitized synthetic sample).

Every record is a small typed envelope; the ``raw`` payload is always retained
verbatim so original history is never lost or silently reshaped.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...contracts.digest import sha256_digest

LEGACY_DB_NAME = "legacy.sqlite"
RECORDS_JSONL_NAME = "records.jsonl"

# Synthetic legacy table -> (legacy_type, extra column mapping). This is the
# documented shape of the sanitized sample DB only; the real old-kernel schema
# is read-only and is never assumed here.
LEGACY_TABLES: dict[str, str] = {
    "projects": "project",
    "tasks": "task",
    "attempts": "attempt",
    "approvals": "approval",
    "evidence": "evidence",
    "files": "file",
}


@dataclass(frozen=True)
class LegacyRecord:
    legacy_type: str
    legacy_id: str
    source_digest: str
    raw: dict[str, Any]
    owner_project_ref: str | None = None
    parent_refs: tuple[str, ...] = ()
    attempt_status: str | None = None
    selected: bool | None = None
    approval_decision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    file_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "legacy_type": self.legacy_type,
            "legacy_id": self.legacy_id,
            "source_digest": self.source_digest,
            "raw": self.raw,
        }
        if self.owner_project_ref is not None:
            d["owner_project_ref"] = self.owner_project_ref
        if self.parent_refs:
            d["parent_refs"] = list(self.parent_refs)
        if self.attempt_status is not None:
            d["attempt_status"] = self.attempt_status
        if self.selected is not None:
            d["selected"] = self.selected
        if self.approval_decision is not None:
            d["approval_decision"] = self.approval_decision
        if self.evidence_refs:
            d["evidence_refs"] = list(self.evidence_refs)
        if self.file_refs:
            d["file_refs"] = list(self.file_refs)
        return d


@dataclass(frozen=True)
class LegacySnapshot:
    """Provider-returned immutable snapshot bound to its exact ledger reference."""

    ref: Any
    digest: str
    source_store_id: str
    records: tuple[LegacyRecord, ...]
    manifest: Any
    producer_principal_id: str

    def digest_body(self) -> dict[str, Any]:
        return {"source_store_id": self.source_store_id,
                "manifest_digest": self.manifest.digest,
                "records": [record.to_dict() for record in self.records]}


def _derive_parent_refs(legacy_type: str, row: dict[str, Any]) -> tuple[str, ...]:
    """Parent lineage for orphan/missing-history detection.

    task/attempt/approval/evidence carry their upstream id in a denormalized
    foreign-key column; project and file are roots/leaves without parents.
    """
    if legacy_type == "task":
        v = row.get("project_id")
    elif legacy_type in ("attempt", "approval"):
        v = row.get("task_id")
    elif legacy_type == "evidence":
        v = row.get("attempt_id")
    else:
        v = None
    return () if v is None else (str(v),)


def _record_from_row(legacy_type: str, row: dict[str, Any]) -> LegacyRecord:
    legacy_id = str(row.get("legacy_id") or row.get("id") or "")
    raw = dict(row)
    return LegacyRecord(
        legacy_type=legacy_type,
        legacy_id=legacy_id,
        source_digest=sha256_digest(raw),
        raw=raw,
        owner_project_ref=_opt(row.get("project_id")),
        parent_refs=_derive_parent_refs(legacy_type, row),
        attempt_status=_opt(row.get("status")),
        selected=_opt_bool(row.get("selected")),
        approval_decision=_opt(row.get("decision")),
        evidence_refs=_refs(row.get("evidence_refs")),
        file_refs=_refs(row.get("file_refs")),
    )


def _record_from_envelope(env: dict[str, Any]) -> LegacyRecord:
    raw = env.get("raw") if isinstance(env.get("raw"), dict) else dict(env)
    return LegacyRecord(
        legacy_type=str(env["legacy_type"]),
        legacy_id=str(env["legacy_id"]),
        source_digest=str(env.get("source_digest") or sha256_digest(raw)),
        raw=raw,
        owner_project_ref=_opt(env.get("owner_project_ref")),
        parent_refs=_refs(env.get("parent_refs")),
        attempt_status=_opt(env.get("attempt_status")),
        selected=_opt_bool(env.get("selected")),
        approval_decision=_opt(env.get("approval_decision")),
        evidence_refs=_refs(env.get("evidence_refs")),
        file_refs=_refs(env.get("file_refs")),
    )


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes")


def _refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return (str(value),)


class LegacyReader:
    """Read-only access to a legacy source directory."""

    def __init__(self, source_root: Path, source_store_id: str):
        self.source_root = Path(source_root)
        self.source_store_id = source_store_id

    def read(self) -> tuple[LegacyRecord, ...]:
        db = self.source_root / LEGACY_DB_NAME
        jsonl = self.source_root / RECORDS_JSONL_NAME
        if db.exists():
            return self._read_sqlite(db)
        if jsonl.exists():
            records: list[LegacyRecord] = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                records.append(_record_from_envelope(json.loads(line)))
            return tuple(records)
        return ()

    def _read_sqlite(self, db: Path) -> tuple[LegacyRecord, ...]:
        uri = f"file:{db.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        try:
            conn.execute("PRAGMA query_only = ON")
            records: list[LegacyRecord] = []
            for table, legacy_type in LEGACY_TABLES.items():
                if not self._table_exists(conn, table):
                    continue
                cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
                for row in conn.execute(f'SELECT * FROM "{table}"').fetchall():
                    records.append(_record_from_row(legacy_type, dict(zip(cols, row))))
            return tuple(records)
        finally:
            conn.close()

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None


class SyntheticLegacySample:
    """Deterministic sanitized synthetic legacy sample (fixture/test-only).

    This is *not* the real old kernel; it exists so the migration capability
    can be exercised against a real SQLite file in a temporary directory.
    """

    SAMPLE_ROWS: dict[str, list[dict[str, Any]]] = {
        "projects": [
            {"legacy_id": "p-a", "display_name": "Alpha", "canonical_root": "D:/old/alpha"},
            {"legacy_id": "p-b", "display_name": "Alpha", "canonical_root": "D:/old/beta"},
        ],
        "tasks": [
            {"legacy_id": "t-1", "project_id": "p-a", "title": "Fix login", "phase": "closed"},
            {"legacy_id": "t-2", "project_id": "p-a", "title": "Add export", "phase": "executing"},
            {"legacy_id": "t-3", "project_id": "p-missing", "title": "Unmapped owner",
             "phase": "draft"},
            {"legacy_id": "t-4", "project_id": "p-a", "title": "Orphan attempt",
             "phase": "executing"},
        ],
        "attempts": [
            {"legacy_id": "a-1", "task_id": "t-1", "project_id": "p-a",
             "status": "completed", "selected": True,
             "usage_amount": "1.25", "usage_unit": "usd"},
            {"legacy_id": "a-2", "task_id": "t-1", "project_id": "p-a",
             "status": "failed", "selected": False},
            {"legacy_id": "a-3", "task_id": "t-2", "project_id": "p-a",
             "status": "failed", "selected": False},
            {"legacy_id": "a-orphan", "task_id": "t-not-found", "project_id": "p-a",
             "status": "failed", "selected": False},
        ],
        "approvals": [
            {"legacy_id": "ap-1", "task_id": "t-1", "project_id": "p-a",
             "decision": "approved", "snapshot_digest": "0" * 64},
        ],
        "evidence": [
            {"legacy_id": "e-1", "attempt_id": "a-1", "project_id": "p-a",
             "sha256": "0" * 64, "path": "out/ok.txt"},
            {"legacy_id": "e-2", "attempt_id": "a-2", "project_id": "p-a",
             "sha256": "1" * 64, "path": "out/err.txt"},
            {"legacy_id": "e-orphan", "attempt_id": "a-missing", "project_id": "p-a",
             "sha256": "2" * 64, "path": "out/gone.txt"},
        ],
        "files": [
            {"legacy_id": "f-1", "project_id": "p-a", "sha256": "3" * 64,
             "path": "src/main.py"},
        ],
    }

    def build_sqlite(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            for table, rows in self.SAMPLE_ROWS.items():
                cols = sorted({k for row in rows for k in row.keys()})
                coldef = ", ".join(f'"{c}" TEXT' for c in cols)
                conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({coldef})')
                for row in rows:
                    keys = list(cols)
                    placeholders = ", ".join("?" for _ in keys)
                    quoted = ", ".join(f'"{c}"' for c in keys)
                    conn.execute(
                        f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
                        [str(row.get(k, "")) for k in keys],
                    )
            conn.commit()
        finally:
            conn.close()
        return path

    def build_jsonl(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        reader_src = path.parent / LEGACY_DB_NAME
        tmp_db = self.build_sqlite(reader_src)
        try:
            records = LegacyReader(path.parent, "legacy-sample").read()
        finally:
            tmp_db.unlink(missing_ok=True)
        lines = [json.dumps(r.to_dict(), ensure_ascii=False, sort_keys=True)
                 for r in records]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
