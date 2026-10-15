"""Identity registry (shared.sqlite): provisioning, binding, stamp and reconcile.

Cross-database provisioning is intentionally not atomic; each step persists a
provision_request_id and reconcile recovers it. Business writes to a project
store are refused until the project is active.
"""
from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...contracts.errors import KernelError, permission_denied, scope_mismatch
from ..store import migrations, schema as s
from ..store.store import PROJECT_MIGRATIONS, Store
from .command_ledger import IDENTITY_COMMAND_MIGRATION, IdentityCommandLedger

IDENTITY_MIGRATIONS: list[tuple[str, str]] = [
    ("0001_initial_identity_schema", s.IDENTITY_DDL),
    ("0002_shared_knowledge_domain", s.SHARED_KNOWLEDGE_DDL),
    IDENTITY_COMMAND_MIGRATION,
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _schema_stamp() -> str:
    return hashlib.sha256(s.PROJECT_DDL.encode("utf-8")).hexdigest()


def _project_dir_name(project_id: str) -> str:
    """Keep lowercase IDs readable; hash the rest to avoid Windows path aliases."""
    reserved_prefix = "_id_"
    safe = (project_id.isascii() and project_id == project_id.lower()
            and project_id not in {".", ".."} and project_id.rstrip(" .") == project_id
            and not project_id.startswith(reserved_prefix)
            and not any(char in project_id for char in '<>:"/\\|?*')
            and not any(ord(char) < 32 for char in project_id)
            and project_id.split(".", 1)[0].upper() not in {
                "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))})
    if safe:
        return project_id
    return reserved_prefix + hashlib.sha256(project_id.encode("utf-8")).hexdigest()


def _reject_reparse_path(path: Path) -> None:
    """Reject links and Windows junctions at a path used for SQLite or manifests."""
    try:
        attributes = os.stat(path, follow_symlinks=False).st_file_attributes
    except AttributeError:
        attributes = 0
    except FileNotFoundError:
        attributes = 0
    if path.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise KernelError(scope_mismatch("identity storage paths may not be links or junctions"))


class IdentityRegistry:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.shared_path = self.data_root / "shared.sqlite"
        _reject_reparse_path(self.shared_path)
        self.conn = sqlite3.connect(str(self.shared_path), isolation_level=None)
        self.conn.execute("PRAGMA foreign_keys = ON")
        migrations.apply_migrations(self.conn, IDENTITY_MIGRATIONS)
        self.store_id = self._ensure_store_id()
        self.command_ledger = IdentityCommandLedger(self.conn, self.store_id)

    def _ensure_store_id(self) -> str:
        rows = self.conn.execute("SELECT store_id FROM identity_meta").fetchall()
        if len(rows) > 1:
            raise KernelError(scope_mismatch("identity registry has multiple store identity rows"))
        if rows:
            return str(rows[0][0])
        store_id = "identity-" + uuid.uuid4().hex
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            rows = self.conn.execute("SELECT store_id FROM identity_meta").fetchall()
            if len(rows) > 1:
                raise KernelError(scope_mismatch("identity registry has multiple store identity rows"))
            if rows:
                self.conn.execute("COMMIT")
                return str(rows[0][0])
            self.conn.execute("INSERT INTO identity_meta (store_id, commit_seq) VALUES (?,0)",
                              (store_id,))
            self.conn.execute("COMMIT")
            return store_id
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.conn.close()

    def _next_seq(self) -> int:
        return self.command_ledger.next_commit_seq()

    # -- provisioning ------------------------------------------------------
    def begin_provision(self, principal_id: str, project_id: str, display_name: str,
                        canonical_root: str, request_id: str) -> dict[str, Any]:
        """Record the durable provisioning intent inside the caller transaction."""
        if self.project_state(project_id) is not None:
            raise KernelError(scope_mismatch(
                f"project {project_id} already exists; use its original provision request"))
        store_id = "store-" + uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO identity_project (project_id,display_name,state,store_id,canonical_root,"
            "schema_stamp,created_at) VALUES (?,?,?,?,?,?,?)",
            (project_id, display_name, "provisioning", store_id, canonical_root,
             _schema_stamp(), _utc_now()))
        seq = self._next_seq()
        receipt = {"provision_request_id": request_id, "state": "provisioning",
                   "project_id": project_id, "store_id": store_id}
        self.conn.execute(
            "INSERT INTO provision_receipt (provision_request_id,principal_id,project_id,state,"
            "store_id,manifest_ref,commit_seq,receipt_json) VALUES (?,?,?,?,?,?,?,?)",
            (request_id, principal_id, project_id, "provisioning", store_id, None, seq,
             json.dumps(receipt, ensure_ascii=False)))
        self.command_ledger.save_commit_seq(seq)
        return receipt

    def provision(self, principal_id: str, project_id: str, display_name: str,
                  canonical_root: str, host_id: str, workspace_id: str | None = None,
                  request_id: str | None = None) -> dict[str, Any]:
        request_id = request_id or "pr-" + uuid.uuid4().hex
        existing = self.conn.execute("SELECT state, canonical_root, store_id FROM identity_project"
                                     " WHERE project_id=?", (project_id,)).fetchone()
        if existing is not None:
            state, root, _ = existing
            if state == "provisioning":
                return self._receipt_for_project(project_id)
            if root != canonical_root:
                raise KernelError(scope_mismatch(
                    f"project {project_id} exists with a different canonical_root"))
            return self._receipt_for_project(project_id)

        stamp = _schema_stamp()
        store_id = "store-" + uuid.uuid4().hex
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "INSERT INTO identity_project (project_id, display_name, state, store_id,"
                " canonical_root, schema_stamp, created_at) VALUES (?,?,?,?,?,?,?)",
                (project_id, display_name, "provisioning", store_id, canonical_root, stamp, _utc_now()))
            seq = self._next_seq()
            receipt = {"provision_request_id": request_id, "state": "provisioning",
                       "project_id": project_id, "store_id": store_id}
            self.conn.execute(
                "INSERT INTO provision_receipt (provision_request_id, principal_id, project_id,"
                " state, store_id, manifest_ref, commit_seq, receipt_json) VALUES (?,?,?,?,?,?,?,?)",
                (request_id, principal_id, project_id, "provisioning", store_id, None, seq,
                 json.dumps(receipt, ensure_ascii=False)))
            self.command_ledger.save_commit_seq(seq)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

        self._create_project_store(project_id, store_id, canonical_root)

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute("UPDATE identity_project SET state='active' WHERE project_id=?",
                              (project_id,))
            receipt["state"] = "active"
            self.conn.execute("UPDATE provision_receipt SET state='active', receipt_json=?"
                              " WHERE provision_request_id=?",
                              (json.dumps(receipt, ensure_ascii=False), request_id))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return receipt

    def _create_project_store(self, project_id: str, store_id: str, canonical_root: str,
                              created_at: str | None = None) -> None:
        proj_dir = self._project_dir(project_id)
        proj_dir.mkdir(parents=True, exist_ok=True)
        _reject_reparse_path(proj_dir)
        proj_dir = proj_dir.resolve()
        created_at = created_at or _utc_now()
        project_store = proj_dir / "project.sqlite"
        _reject_reparse_path(project_store)
        store = Store.open_project(project_store, project_id, store_id)
        try:
            store.set_project_meta(project_id, store_id, migrations.SCHEMA_VERSION, created_at)
            project_meta = store.get_project_meta()
            manifest = {"project_id": project_id, "store_id": store_id,
                        "schema_stamp": _schema_stamp(), "canonical_root": canonical_root,
                        "created_at": project_meta["created_at"]}
            manifest_path = proj_dir / "project-manifest.json"
            _reject_reparse_path(manifest_path)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            store.close()

    def _project_dir(self, project_id: str) -> Path:
        projects_path = self.data_root / "projects"
        _reject_reparse_path(projects_path)
        projects_root = projects_path.resolve()
        if not projects_root.is_relative_to(self.data_root):
            raise KernelError(scope_mismatch("projects directory resolves outside identity data root"))
        project_dir = projects_root / _project_dir_name(project_id)
        _reject_reparse_path(project_dir)
        resolved = project_dir.resolve()
        if (not resolved.is_relative_to(projects_root)
                or (project_dir.exists() and resolved != project_dir)):
            raise KernelError(scope_mismatch("project directory resolves outside identity data root"))
        return project_dir

    def _receipt_for_project(self, project_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT receipt_json FROM provision_receipt WHERE project_id=?"
            " ORDER BY commit_seq DESC LIMIT 1", (project_id,)).fetchone()
        if row is None:
            raise KernelError(scope_mismatch(f"no provision receipt for {project_id}"))
        return json.loads(row[0])

    def reconcile(self, provision_request_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT project_id, state, store_id, receipt_json FROM provision_receipt"
            " WHERE provision_request_id=?", (provision_request_id,)).fetchone()
        if row is None:
            raise KernelError(scope_mismatch(f"unknown provision request {provision_request_id}"))
        project_id, state, store_id, receipt_json = row
        project_row = self.conn.execute(
            "SELECT display_name, canonical_root, schema_stamp, created_at FROM identity_project WHERE project_id=?",
            (project_id,)).fetchone()
        if project_row is None:
            raise KernelError(scope_mismatch(f"identity project missing for {project_id}"))
        proj_dir = self._project_dir(project_id)
        proj_store = proj_dir / "project.sqlite"
        if not proj_store.exists():
            if state == "active":
                raise KernelError(scope_mismatch(
                    f"active project {project_id} store is missing; refusing to recreate its history"))
            self._create_project_store(project_id, store_id, project_row[1], project_row[3])
        self._validate_project_artifacts(project_id, store_id, project_row[1],
                                         project_row[2], project_row[3], proj_dir, proj_store)
        receipt = json.loads(receipt_json)
        owned_transaction = not self.conn.in_transaction
        if owned_transaction:
            self.conn.execute("BEGIN IMMEDIATE")
        try:
            latest = self.conn.execute(
                "SELECT state,receipt_json FROM provision_receipt WHERE provision_request_id=?",
                (provision_request_id,)).fetchone()
            if latest is None:
                raise KernelError(scope_mismatch(f"unknown provision request {provision_request_id}"))
            state, receipt_json = latest
            receipt = json.loads(receipt_json)
            if state != "active":
                self.conn.execute("UPDATE identity_project SET state='active' WHERE project_id=?",
                                  (project_id,))
                receipt["state"] = "active"
                self.conn.execute("UPDATE provision_receipt SET state='active', receipt_json=?"
                                  " WHERE provision_request_id=?",
                                  (json.dumps(receipt, ensure_ascii=False), provision_request_id))
            if owned_transaction:
                self.conn.execute("COMMIT")
        except BaseException:
            if owned_transaction and self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise
        return receipt

    def _validate_project_artifacts(self, project_id: str, store_id: str,
                                    canonical_root: str, schema_stamp: str,
                                    created_at: str,
                                    project_dir: Path, project_store: Path) -> None:
        """Refuse activation unless the project DB and manifest match the intent."""
        manifest_path = project_dir / "project-manifest.json"
        try:
            _reject_reparse_path(project_store)
            _reject_reparse_path(manifest_path)
            conn = sqlite3.connect(project_store.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    raise ValueError("project database integrity check failed")
                migrations.verify_migrations(conn, PROJECT_MIGRATIONS)
                meta_rows = conn.execute(
                    "SELECT project_id,store_id,schema_version,created_at FROM project_meta").fetchall()
            finally:
                conn.close()
            if len(meta_rows) != 1:
                raise ValueError("project database must have exactly one identity row")
            meta = meta_rows[0]
            expected_stamp = _schema_stamp()
            if (tuple(meta[:2]) != (project_id, store_id)
                    or meta[2] != migrations.SCHEMA_VERSION
                    or not isinstance(meta[3], str) or not meta[3]
                    or schema_stamp != expected_stamp):
                raise ValueError("project database identity differs from provisioning intent")
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            else:
                manifest = {"project_id": project_id, "store_id": store_id,
                    "schema_stamp": schema_stamp, "canonical_root": canonical_root,
                    "created_at": meta[3]}
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
            if manifest != {"project_id": project_id, "store_id": store_id,
                        "schema_stamp": expected_stamp, "canonical_root": canonical_root,
                        "created_at": meta[3]}:
                raise ValueError("project database or manifest differs from provisioning intent")
        except (OSError, sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise KernelError(scope_mismatch(
                f"project {project_id} artifacts are incomplete or inconsistent; provisioning remains pending")) from exc

    def project_for_provision_request(self, provision_request_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT project_id FROM provision_receipt WHERE provision_request_id=?",
            (provision_request_id,)).fetchone()
        return str(row[0]) if row else None

    # -- binding -----------------------------------------------------------
    def bind(self, project_id: str, host_id: str, binding_kind: str, canonical_key: str,
             expected_binding_version: str) -> dict[str, Any]:
        existing = self.conn.execute(
            "SELECT project_id, binding_version FROM identity_binding"
            " WHERE host_id=? AND binding_kind=? AND canonical_key=?",
            (host_id, binding_kind, canonical_key)).fetchone()
        if existing is not None:
            other_project, version = existing
            if other_project != project_id:
                raise KernelError(scope_mismatch(
                    f"binding already maps to project {other_project}"))
            if version != expected_binding_version:
                raise KernelError(scope_mismatch(
                    f"binding version conflict: expected {expected_binding_version}, actual {version}"))
            return {"project_id": project_id, "binding_version": version, "unchanged": True}
        state = self.project_state(project_id)
        if state != "active":
            raise KernelError(scope_mismatch(
                f"project {project_id} is {state or 'unknown'} and cannot be bound"))
        self.conn.execute(
            "INSERT INTO identity_binding (host_id, binding_kind, canonical_key, project_id,"
            " binding_version) VALUES (?,?,?,?,?)",
            (host_id, binding_kind, canonical_key, project_id, expected_binding_version))
        if not self.conn.in_transaction:
            self.conn.commit()
        return {"project_id": project_id, "binding_version": expected_binding_version,
                "unchanged": False}

    # -- state -------------------------------------------------------------
    def project_state(self, project_id: str) -> str | None:
        row = self.conn.execute("SELECT state FROM identity_project WHERE project_id=?",
                                (project_id,)).fetchone()
        return row[0] if row else None

    def require_active(self, project_id: str) -> None:
        state = self.project_state(project_id)
        if state != "active":
            raise KernelError(permission_denied(
                f"project {project_id} is {state or 'unknown'}; writes refused before active"))
