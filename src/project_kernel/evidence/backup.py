"""WAL-consistent SQLite backup, verification and restore planning (P05).

Design contract 02 §6 / 04 §4 / 09 §2:

* ``backup_create`` uses ``sqlite3.Connection.backup`` to produce a consistent
  copy (committed WAL content included, no ``copy2`` of a live main DB), then
  runs ``integrity_check``, ``foreign_key_check``, schema/migration version
  checks, cross-table reference checks and artifact manifest verification on
  the copy before writing the ``BackupManifest`` and a registry audit line.
* ``verify_backup_file`` performs the same real checks against an existing
  backup file (used by disaster restore).
* ``restore_plan`` distinguishes business restore (new revision, history kept,
  no fence) from disaster restore (writer fence, human decision, verified
  replacement).

First release scope: restore **plans** and their verification are implemented;
``restore_apply`` never replaces the live store. It returns an explicit
``not_implemented`` receipt (or refuses without a writer fence / human
decision) instead of reporting a success it did not perform.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..contracts import sha256_digest
from ..contracts.dto import ArtifactRef
from ..contracts.errors import (
    KernelError,
    approval_required,
    capability_unavailable,
    invalid_input,
)
from ..data.store.store import Store

_READ_CHUNK = 65536

BUSINESS_REVISION = "business_revision"
DISASTER_RECOVERY = "disaster_recovery"

_KIND_ALIASES = {
    "business": BUSINESS_REVISION,
    "business_revision": BUSINESS_REVISION,
    "disaster": DISASTER_RECOVERY,
    "disaster_recovery": DISASTER_RECOVERY,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    store_id: str
    schema_version: str
    created_at: str
    source_db: str
    integrity_ok: bool
    foreign_keys_ok: bool
    file_sha256: str
    canonicalization: str = "rfc8785"
    file_bytes: int = 0
    backup_path: str = ""
    versions_ok: bool = True
    references_ok: bool = True
    artifacts_ok: bool = True
    migrations: tuple[tuple[str, str], ...] = ()
    reference_problems: tuple[str, ...] = ()
    artifact_problems: tuple[str, ...] = ()

    @property
    def all_ok(self) -> bool:
        return bool(self.integrity_ok and self.foreign_keys_ok and self.versions_ok
                    and self.references_ok and self.artifacts_ok)

    def body(self) -> dict[str, Any]:
        return {"backup_id": self.backup_id, "store_id": self.store_id,
                "schema_version": self.schema_version, "created_at": self.created_at,
                "source_db": self.source_db, "integrity_ok": self.integrity_ok,
                "foreign_keys_ok": self.foreign_keys_ok, "file_sha256": self.file_sha256,
                "canonicalization": self.canonicalization, "file_bytes": self.file_bytes,
                "backup_path": self.backup_path, "versions_ok": self.versions_ok,
                "references_ok": self.references_ok, "artifacts_ok": self.artifacts_ok,
                "migrations": [list(m) for m in self.migrations],
                "reference_problems": list(self.reference_problems),
                "artifact_problems": list(self.artifact_problems),
                "all_ok": self.all_ok}

    def digest(self) -> str:
        return sha256_digest(self.body())


# --------------------------------------------------------------------------- checks

def _read_only(path: Path) -> sqlite3.Connection:
    """Read the copy without writing to it; fall back to immutable for WAL copies
    that can no longer create a ``-shm`` sidecar, and for corrupt images."""
    p = Path(path).as_posix()
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, isolation_level=None)
    try:
        conn.execute("PRAGMA schema_version").fetchone()
        return conn
    except sqlite3.DatabaseError:
        conn.close()
    return sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True, isolation_level=None)


def _integrity_check(path: Path) -> tuple[bool, str]:
    conn = _read_only(path)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        ok = row is not None and row[0] == "ok"
        return ok, "" if ok else str(row[0] if row else "no result")
    except sqlite3.DatabaseError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()


def _foreign_key_check(path: Path) -> tuple[bool, str]:
    conn = _read_only(path)
    try:
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        return len(rows) == 0, "" if not rows else f"{len(rows)} violations"
    except sqlite3.DatabaseError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()


def _migrations(conn: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    try:
        rows = conn.execute(
            "SELECT migration_id, checksum FROM schema_migration ORDER BY migration_id").fetchall()
    except sqlite3.DatabaseError:
        return ()
    return tuple((str(r[0]), str(r[1])) for r in rows)


#: cross-table reference checks: every row on the right side must have its parent
_REFERENCE_CHECKS: tuple[tuple[str, str], ...] = (
    ("entity_head -> revision",
     "SELECT COUNT(*) FROM entity_head h LEFT JOIN revision r"
     " ON r.project_id=h.project_id AND r.type=h.type AND r.object_id=h.object_id"
     " AND r.revision_id=h.revision_id WHERE r.revision_id IS NULL"),
    ("head_history -> revision",
     "SELECT COUNT(*) FROM head_history h LEFT JOIN revision r"
     " ON r.project_id=h.project_id AND r.type=h.type AND r.object_id=h.object_id"
     " AND r.revision_id=h.revision_id WHERE r.revision_id IS NULL"),
    ("revision -> entity",
     "SELECT COUNT(*) FROM revision v LEFT JOIN entity e"
     " ON e.project_id=v.project_id AND e.type=v.type AND e.object_id=v.object_id"
     " WHERE e.object_id IS NULL"),
    ("entity_head -> entity",
     "SELECT COUNT(*) FROM entity_head h LEFT JOIN entity e"
     " ON e.project_id=h.project_id AND e.type=h.type AND e.object_id=h.object_id"
     " WHERE e.object_id IS NULL"),
    ("archive_manifest -> commit_log",
     "SELECT COUNT(*) FROM archive_manifest m LEFT JOIN commit_log c"
     " ON c.commit_seq=m.commit_seq WHERE c.commit_seq IS NULL"),
    ("sink_receipt -> archive_manifest",
     "SELECT COUNT(*) FROM sink_receipt s LEFT JOIN archive_manifest m"
     " ON m.project_id=s.project_id AND m.manifest_id=s.manifest_id"
     " WHERE m.manifest_id IS NULL"),
    ("delivery_operation -> delivery_snapshot",
     "SELECT COUNT(*) FROM delivery_operation o LEFT JOIN delivery_snapshot s"
     " ON s.project_id=o.project_id AND s.snapshot_id=o.snapshot_id"
     " WHERE s.snapshot_id IS NULL"),
    ("approval_index -> delivery_snapshot",
     "SELECT COUNT(*) FROM approval_index a LEFT JOIN delivery_snapshot s"
     " ON s.project_id=a.project_id AND s.snapshot_id=a.snapshot_id"
     " WHERE s.snapshot_id IS NULL"),
)


def _reference_problems(conn: sqlite3.Connection) -> list[str]:
    problems: list[str] = []
    for name, sql in _REFERENCE_CHECKS:
        try:
            row = conn.execute(sql).fetchone()
        except sqlite3.DatabaseError:
            continue  # table absent in this schema revision
        count = int(row[0]) if row else 0
        if count:
            problems.append(f"{name}: {count} orphan rows")
    return problems


def _artifact_problems(artifact_store: Any,
                       refs: Iterable[ArtifactRef]) -> list[str]:
    problems: list[str] = []
    for ref in refs:
        if artifact_store is None:
            problems.append(f"artifact:{ref.sha256}:no_store_to_verify")
            continue
        result = artifact_store.verify(ref, isolate=False)
        if not result["ok"]:
            problems.append(f"artifact:{ref.sha256}:{result['reason']}")
    return problems


def artifacts_from_rows(conn: sqlite3.Connection) -> list[ArtifactRef]:
    """Read artifact evidence from both the typed index and immutable revisions."""
    refs={}
    for artifact_id,digest,size,mime in conn.execute("SELECT artifact_id,digest,size,mime FROM artifact"):
        ref=ArtifactRef(str(artifact_id),str(digest),str(size),str(mime),True)
        refs[(ref.artifact_id,ref.sha256)]=ref
    def visit(value):
        if isinstance(value,dict):
            if {"artifact_id","sha256","size_bytes","media_type"} <= value.keys():
                ref=ArtifactRef(value["artifact_id"],value["sha256"],str(value["size_bytes"]),value["media_type"],value.get("required",True))
                refs[(ref.artifact_id,ref.sha256)]=ref
            else:
                for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    for row in conn.execute("SELECT payload_json FROM revision"):
        visit(json.loads(row[0]))
    return list(refs.values())


def verify_backup_file(path: Path, *, expected_schema_version: str | None = None,
                       artifact_manifest: Iterable[ArtifactRef] | None = None,
                       artifact_store: Any = None,
                       source_conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Real verification of a backup copy: integrity, FK, versions, refs, artifacts."""
    path = Path(path)
    if not path.is_file():
        raise KernelError(invalid_input(f"backup file {path} missing"))
    integrity_ok, integrity_detail = _integrity_check(path)
    fk_ok, fk_detail = _foreign_key_check(path)
    versions_ok = True
    version_problems: list[str] = []
    migrations: tuple[tuple[str, str], ...] = ()
    schema_version = ""
    reference_problems: list[str] = []
    if not integrity_ok:
        versions_ok = False
        version_problems.append(f"integrity_check failed: {integrity_detail}")
    else:
        conn = _read_only(path)
        try:
            migrations = _migrations(conn)
            try:
                row = conn.execute("SELECT schema_version FROM project_meta LIMIT 1").fetchone()
                schema_version = str(row[0]) if row else ""
            except sqlite3.DatabaseError:
                schema_version = ""
            if expected_schema_version is not None and schema_version != expected_schema_version:
                versions_ok = False
                version_problems.append(
                    f"schema_version {schema_version!r} != expected {expected_schema_version!r}")
            if source_conn is not None:
                source_migrations = _migrations(source_conn)
                if source_migrations and migrations != source_migrations:
                    versions_ok = False
                    version_problems.append("migration set differs from the source store")
            reference_problems = _reference_problems(conn)
        finally:
            conn.close()

    if artifact_manifest is None and integrity_ok:
        conn = _read_only(path)
        try:
            artifact_manifest = artifacts_from_rows(conn)
        finally:
            conn.close()
    artifact_problems = _artifact_problems(artifact_store, artifact_manifest or ())

    return {
        "integrity_ok": integrity_ok,
        "integrity_detail": integrity_detail,
        "foreign_keys_ok": fk_ok,
        "foreign_keys_detail": fk_detail,
        "versions_ok": versions_ok,
        "version_problems": version_problems,
        "schema_version": schema_version,
        "migrations": migrations,
        "references_ok": not reference_problems,
        "reference_problems": reference_problems,
        "artifacts_ok": not artifact_problems,
        "artifact_problems": artifact_problems,
    }


# ------------------------------------------------------------------------ backup

def _append_registry_audit(backup_root: Path, entry: dict[str, Any]) -> None:
    with open(backup_root / "registry.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def backup_create(store: Store, backup_root: Path, *,
                  artifact_manifest: Iterable[ArtifactRef] | None = None,
                  artifact_store: Any = None,
                  policy_ref: str | None = None) -> BackupManifest:
    """Consistent SQLite copy + real checks; writes manifest and registry audit."""
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_id = "bkp-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + \
        uuid.uuid4().hex[:8]
    dest = backup_root / f"{backup_id}.sqlite"

    source_db = str(store.conn.execute("PRAGMA database_list").fetchone()[2])
    target = sqlite3.connect(str(dest))
    try:
        # consistent copy: committed WAL content is included, no live-file copy
        store.conn.backup(target)
    finally:
        target.close()

    # fold any copy-side WAL into the main file so file_sha256 is stable
    conn = sqlite3.connect(str(dest))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    for suffix in ("-wal", "-shm", "-journal"):
        leftover = dest.with_name(dest.name + suffix)
        if leftover.exists():
            leftover.unlink()

    checks = verify_backup_file(dest, artifact_manifest=artifact_manifest,
                                artifact_store=artifact_store, source_conn=store.conn)
    file_sha256 = _file_sha256(dest)
    manifest = BackupManifest(
        backup_id=backup_id, store_id=store.store_id,
        schema_version=checks["schema_version"] or "1.0.0", created_at=_utc_now(),
        source_db=source_db, integrity_ok=checks["integrity_ok"],
        foreign_keys_ok=checks["foreign_keys_ok"], file_sha256=file_sha256,
        file_bytes=dest.stat().st_size, backup_path=str(dest),
        versions_ok=checks["versions_ok"], references_ok=checks["references_ok"],
        artifacts_ok=checks["artifacts_ok"], migrations=checks["migrations"],
        reference_problems=tuple(checks["reference_problems"]),
        artifact_problems=tuple(checks["artifact_problems"]))
    (backup_root / f"{backup_id}.manifest.json").write_text(
        json.dumps(manifest.body(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _append_registry_audit(backup_root, {
        "event": "backup.created", "backup_id": backup_id, "store_id": store.store_id,
        "policy_ref": policy_ref, "source_db": source_db, "file_sha256": file_sha256,
        "all_ok": manifest.all_ok, "recorded_at": _utc_now()})
    return manifest


# ----------------------------------------------------------------------- restore

@dataclass(frozen=True)
class RestorePlan:
    plan_id: str
    restore_kind: str
    target_ref: str
    reason: str
    mode: str
    preserve_history: bool
    requires_writer_fence: bool
    requires_human_decision: bool
    verification_steps: tuple[str, ...]
    apply_implemented: bool = False
    schema_version: str = "1.0.0"
    canonicalization: str = "rfc8785"

    def body(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "restore_kind": self.restore_kind,
                "target_ref": self.target_ref, "reason": self.reason, "mode": self.mode,
                "preserve_history": self.preserve_history,
                "requires_writer_fence": self.requires_writer_fence,
                "requires_human_decision": self.requires_human_decision,
                "verification_steps": list(self.verification_steps),
                "apply_implemented": self.apply_implemented,
                "schema_version": self.schema_version,
                "canonicalization": self.canonicalization}

    def digest(self) -> str:
        return sha256_digest(self.body())

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "digest": self.digest()}


_BUSINESS_STEPS = ("target revision/digest readable",
                   "new revision published after restore",
                   "pre-restore history retained")
_DISASTER_STEPS = ("all writers stopped and fence held",
                   "backup integrity_check",
                   "backup foreign_key_check",
                   "schema/migration version match",
                   "cross-table reference integrity",
                   "artifact manifest verification",
                   "controlled-path replacement and post-restore verification before unfence")


def restore_plan(restore_kind: str, backup_or_revision_ref: str, *,
                 reason: str = "") -> RestorePlan:
    """Business restore vs disaster restore are explicitly distinguished."""
    kind = _KIND_ALIASES.get(restore_kind)
    if kind is None:
        raise KernelError(invalid_input(f"unknown restore_kind {restore_kind!r}"))
    if kind == BUSINESS_REVISION:
        mode, fence, human, steps = "new_revision", False, False, _BUSINESS_STEPS
    else:
        mode, fence, human, steps = "replace_store", True, True, _DISASTER_STEPS
    plan_id = "plan-" + sha256_digest({"kind": kind, "ref": backup_or_revision_ref,
                                       "reason": reason})[:16]
    return RestorePlan(plan_id=plan_id, restore_kind=kind, target_ref=backup_or_revision_ref,
                       reason=reason, mode=mode, preserve_history=True,
                       requires_writer_fence=fence, requires_human_decision=human,
                       verification_steps=steps)


@dataclass(frozen=True)
class RestoreReceipt:
    plan_id: str
    restore_kind: str
    status: str
    implemented: bool
    mode: str
    writer_fence_held: bool
    human_decision_ref: str | None = None
    backup_path: str | None = None
    verification: dict[str, Any] | None = None
    note: str = ""
    recorded_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"plan_id": self.plan_id, "restore_kind": self.restore_kind,
                             "status": self.status, "implemented": self.implemented,
                             "mode": self.mode, "writer_fence_held": self.writer_fence_held,
                             "recorded_at": self.recorded_at, "note": self.note}
        if self.human_decision_ref is not None:
            d["human_decision_ref"] = self.human_decision_ref
        if self.backup_path is not None:
            d["backup_path"] = self.backup_path
        if self.verification is not None:
            d["verification"] = self.verification
        return d


def restore_verify(plan: RestorePlan, backup_path: Path, *,
                   expected_schema_version: str | None = None,
                   artifact_manifest: Iterable[ArtifactRef] | None = None,
                   artifact_store: Any = None) -> dict[str, Any]:
    """Real verification of the backup referenced by a restore plan."""
    checks = verify_backup_file(Path(backup_path),
                                expected_schema_version=expected_schema_version,
                                artifact_manifest=artifact_manifest,
                                artifact_store=artifact_store)
    return {**checks,
            "ok": bool(checks["integrity_ok"] and checks["foreign_keys_ok"]
                       and checks["versions_ok"] and checks["references_ok"]
                       and checks["artifacts_ok"])}


def restore_apply(plan: RestorePlan, *, human_decision_ref: str | None = None,
                  writer_fence: str | None = None, backup_path: Path | None = None,
                  expected_schema_version: str | None = None,
                  artifact_manifest: Iterable[ArtifactRef] | None = None,
                  artifact_store: Any = None, audit_path: Path | None = None) -> RestoreReceipt:
    """Fence + decision semantics. First release never replaces the live store.

    The store replacement itself is *not implemented* here: this returns an
    explicit ``not_implemented`` receipt and never reports ``applied``. A
    disaster restore without a writer fence or human decision is refused.
    """
    if plan.requires_human_decision and not human_decision_ref:
        _audit(audit_path, {"event": "restore.refused", "plan_id": plan.plan_id,
                            "restore_kind": plan.restore_kind, "reason": "no human decision"})
        raise KernelError(approval_required())
    verification: dict[str, Any] | None = None
    if plan.restore_kind == DISASTER_RECOVERY and backup_path is not None:
        verification = restore_verify(plan, backup_path,
                                     expected_schema_version=expected_schema_version,
                                     artifact_manifest=artifact_manifest,
                                     artifact_store=artifact_store)
    if plan.requires_writer_fence and not writer_fence:
        _audit(audit_path, {"event": "restore.refused", "plan_id": plan.plan_id,
                            "restore_kind": plan.restore_kind, "reason": "no writer fence",
                            "verification_ok": None if verification is None else verification["ok"]})
        raise KernelError(capability_unavailable(
            "disaster restore refused: all writers must be stopped and a writer fence held"
            " before any replacement"))
    note = ("first release implements restore plans and verification only; the live store is"
            " never replaced by this call. Replacement requires the fenced maintenance path"
            " and post-restore verification before unfence.")
    receipt = RestoreReceipt(plan_id=plan.plan_id, restore_kind=plan.restore_kind,
                             status="not_implemented", implemented=False, mode=plan.mode,
                             writer_fence_held=bool(writer_fence),
                             human_decision_ref=human_decision_ref,
                             backup_path=str(backup_path) if backup_path is not None else None,
                             verification=verification, note=note)
    _audit(audit_path, {"event": "restore.recorded", **receipt.to_dict()})
    return receipt


def _audit(audit_path: Path | None, entry: dict[str, Any]) -> None:
    if audit_path is None:
        return
    path = Path(audit_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
