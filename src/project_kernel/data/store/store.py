"""Store: the only SQLite writer for project data (P01 owner).

Opens one connection per project DB. Read/write access goes through the typed
repository methods and the UnitOfWork; no generic UPDATE interface is exposed.
Read-only connections refuse all writes and never run DDL.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ...contracts.dto import ObjectRef
from ...contracts.errors import KernelError, permission_denied, reference_not_found, scope_mismatch, schema_incompatible
from . import migrations
from .schema import FLOW_DOMAIN_DDL, LEGACY_KNOWLEDGE_DDL, PROJECT_DDL

PROJECT_MIGRATIONS: list[tuple[str, str]] = [
    ("0001_initial_project_schema", PROJECT_DDL),
    ("0002_flow_domain_tables", FLOW_DOMAIN_DDL),
    ("0003_legacy_knowledge_tables", LEGACY_KNOWLEDGE_DDL),
]


class Store:
    def __init__(self, conn: sqlite3.Connection, project_id: str, store_id: str,
                 read_only: bool = False):
        self.conn = conn
        self.project_id = project_id
        self.store_id = store_id
        self.read_only = read_only
        self._access_fence = None

    # -- lifecycle ---------------------------------------------------------
    @classmethod
    def open_project(cls, path: Path, project_id: str, store_id: str,
                     read_only: bool = False) -> "Store":
        if str(path) == ":memory:":
            if read_only:
                raise KernelError(permission_denied("an in-memory project cannot be reopened read-only"))
            return cls._open_project_connection(path, project_id, store_id, read_only=False)
        path = Path(path).resolve()
        if not read_only:
            from .access_fence import ProjectAccessFence
            fence = ProjectAccessFence(path)
            try:
                store = cls._open_project_connection(path, project_id, store_id, read_only=False)
            except BaseException:
                fence.close()
                raise
            store._access_fence = fence
            return store
        return cls._open_project_connection(path, project_id, store_id, read_only=True)

    @classmethod
    def _open_project_connection(cls, path, project_id, store_id, read_only):
        conn = None
        try:
            if read_only:
                uri = f"file:{path.as_posix()}?mode=ro"
                conn = sqlite3.connect(uri, uri=True, isolation_level=None)
                conn.execute("PRAGMA query_only = ON")
                conn.execute("PRAGMA foreign_keys = ON")
                migrations.verify_migrations(conn, PROJECT_MIGRATIONS)
            else:
                conn = sqlite3.connect(str(path), isolation_level=None)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA busy_timeout = 5000")
                migrations.apply_migrations(conn, PROJECT_MIGRATIONS)
        except BaseException:
            if conn is not None:
                conn.close()
            raise
        try:
            if not read_only:
                conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT project_id,store_id,schema_version FROM project_meta").fetchall()
            if rows and (len(rows) != 1 or rows[0][:2] != (project_id, store_id)):
                raise KernelError(scope_mismatch("persisted project/store identity differs from requested identity"))
            if rows and rows[0][2] != migrations.SCHEMA_VERSION:
                raise KernelError(schema_incompatible("project schema stamp differs from supported schema version"))
            if not rows:
                projects = {row[0] for row in conn.execute("SELECT DISTINCT project_id FROM entity")}
                if projects - {project_id}:
                    raise KernelError(scope_mismatch("project ledger contains another project's records"))
                if read_only:
                    raise KernelError(scope_mismatch("read-only project store has no persisted identity"))
                from datetime import datetime, timezone
                conn.execute("INSERT INTO project_meta(project_id,store_id,schema_version,created_at) VALUES(?,?,?,?)",
                    (project_id, store_id, migrations.SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()))
            if not read_only:
                conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            conn.close()
            raise
        return cls(conn, project_id, store_id, read_only=read_only)

    def close(self) -> None:
        try:
            self.conn.close()
        finally:
            if self._access_fence is not None:
                self._access_fence.close()
                self._access_fence = None

    def _guard_write(self) -> None:
        if self.read_only:
            raise KernelError(permission_denied("read-only store; writes rejected"))

    # -- sequences ---------------------------------------------------------
    def next_commit_seq(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(commit_seq), 0) + 1 FROM commit_log").fetchone()
        return int(row[0])

    # -- reads -------------------------------------------------------------
    def get_revision(self, ref: ObjectRef) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json, digest, commit_seq, ordinal, payload_schema, principal_id"
            " FROM revision WHERE project_id=? AND type=? AND object_id=? AND revision_id=?",
            (ref.project_id, ref.object_type, ref.object_id, ref.revision_id),
        ).fetchone()
        if row is None:
            return None
        return {"payload": json.loads(row[0]), "digest": row[1], "commit_seq": int(row[2]),
                "ordinal": int(row[3]), "payload_schema": row[4], "principal_id": row[5]}

    def get_head(self, object_type: str, object_id: str, pointer_name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT revision_id, head_version, updated_seq FROM entity_head"
            " WHERE project_id=? AND type=? AND object_id=? AND pointer_name=?",
            (self.project_id, object_type, object_id, pointer_name),
        ).fetchone()
        if row is None:
            return None
        return {"revision_id": row[0], "head_version": int(row[1]), "updated_seq": int(row[2])}

    def head_as_of(self, object_type: str, object_id: str, pointer_name: str,
                   as_of_seq: int) -> str | None:
        """Last revision published to *pointer_name* at or before as_of_seq."""
        row = self.conn.execute(
            "SELECT revision_id FROM head_history"
            " WHERE project_id=? AND type=? AND object_id=? AND pointer_name=? AND commit_seq<=?"
            " ORDER BY commit_seq DESC LIMIT 1",
            (self.project_id, object_type, object_id, pointer_name, as_of_seq),
        ).fetchone()
        return row[0] if row else None

    def get_receipt(self, principal_id: str, idempotency_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT input_hash, receipt_json FROM command_receipt"
            " WHERE principal_id=? AND idempotency_key=?",
            (principal_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return {"input_hash": row[0], "receipt": json.loads(row[1])}

    # -- writes (typed, used by UnitOfWork) --------------------------------
    def set_project_meta(self, project_id: str, store_id: str, schema_version: str,
                         created_at: str) -> None:
        self._guard_write()
        self.conn.execute(
            "INSERT OR IGNORE INTO project_meta (project_id, store_id, schema_version, created_at)"
            " VALUES (?,?,?,?)",
            (project_id, store_id, schema_version, created_at),
        )

    def get_project_meta(self) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT store_id, schema_version, created_at FROM project_meta"
                                " WHERE project_id=?", (self.project_id,)).fetchone()
        return None if row is None else {"store_id": row[0], "schema_version": row[1],
                                         "created_at": row[2]}
