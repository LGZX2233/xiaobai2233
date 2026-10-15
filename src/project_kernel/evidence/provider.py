"""Filesystem evidence provider with no application authorization dependencies.

The application pins inputs and commits its claim before invoking these effects.
Only the separate ControlledStoreRecovery maintenance entry may replace a store;
this provider restores to an unused isolated file and never replays on reconcile.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from ..contracts.errors import KernelError, invalid_input, capability_unavailable, artifact_digest_mismatch
from .backup import backup_create, verify_backup_file

@dataclass(frozen=True)
class IsolatedRestoreTarget:
    """Offline test destination owned exclusively by the kernel maintenance service."""
    root: Path
    target_id: str
    @contextmanager
    def fence(self):
        root=self.root.resolve()
        root.mkdir(parents=True,exist_ok=True)
        lock=root/".restore-fence"
        with lock.open("xb") as f:
            f.write(uuid.uuid4().hex.encode("ascii"))
            f.flush()
            os.fsync(f.fileno())
        try:
            yield root
        finally:
            lock.unlink()

def file_digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

class FileEvidenceProvider:
    """Provide local evidence effects for an explicitly configured project store."""

    def __init__(self, store, *, artifact_storage=None, exporters=None,
                 backup_root=None, restore_target=None):
        self.store = store
        self.storage = artifact_storage
        self.exporters = dict(exporters or {})
        self.backup_root = Path(backup_root).resolve() if backup_root is not None else None
        self.restore_target = restore_target
        self.artifact_available = artifact_storage is not None
        self.sink_ids = frozenset(self.exporters)
        self.backup_available = self.backup_root is not None
        self.restore_target_info = None
        if restore_target is not None:
            self.restore_target_info = {"target_id": restore_target.target_id,
                "restore_mode": "isolated_copy"}
            if hasattr(restore_target, "live_path"):
                self.restore_target_info.update(live_path=str(Path(restore_target.live_path).resolve()),
                    restore_mode="controlled_replacement")

    def register_artifact(self, staged, payload):
        record = self.storage.register(staged["locator"], payload["digest"],
            source_ref=payload["source_ref"], media_type=payload["media_type"])
        return record.to_ref().to_dict()

    def archive(self, manifest, sink_id, operation_id, *, repair, original_effect_id=None):
        exporter = self.exporters[sink_id]
        method = exporter.repair if repair else exporter.export
        return method(manifest, sink_id, lease_token=operation_id,
            original_effect_id=original_effect_id).to_dict()

    def backup(self, operation_id):
        manifest = backup_create(self.store, self.backup_root / operation_id,
            artifact_store=self.storage)
        return manifest.body()

    def _verified_source(self, source):
        src = Path(source["backup_path"]).resolve()
        if (self.backup_root is None or not src.is_relative_to(self.backup_root)
                or file_digest(src) != source["file_sha256"]):
            raise KernelError(artifact_digest_mismatch("backup path or bytes differ"))
        checks = verify_backup_file(src, artifact_store=self.storage, source_conn=self.store.conn)
        if not all(checks[k] for k in ("integrity_ok", "foreign_keys_ok", "versions_ok", "references_ok", "artifacts_ok")):
            raise KernelError(invalid_input("backup verification failed"))
        return src

    def restore(self, source, operation_id):
        if self.restore_target_info is None or self.restore_target_info["restore_mode"] != "isolated_copy":
            raise KernelError(capability_unavailable("provider only restores to an isolated offline copy"))
        src = self._verified_source(source)
        with self.restore_target.fence() as root:
            live = Path(self.store.conn.execute("PRAGMA database_list").fetchone()[2]).resolve()
            dest = root / (operation_id + ".sqlite")
            if dest == live or dest.exists():
                raise KernelError(invalid_input("restore destination must be an unused offline file"))
            stage = root / (operation_id + ".partial")
            with src.open("rb") as inp, stage.open("xb") as out:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
            if file_digest(stage) != source["file_sha256"]:
                raise KernelError(artifact_digest_mismatch("restored copy differs"))
            stage.rename(dest)
            if file_digest(dest) != source["file_sha256"]:
                raise KernelError(artifact_digest_mismatch("published restore differs"))
            return {"status": "succeeded", "restored_path": str(dest),
                "file_sha256": source["file_sha256"], "writer_fence_held": True,
                "mode": "isolated_offline_copy", "original_store_preserved": True}

    def reconcile_archive(self, manifest, sink_id):
        exporter = self.exporters[sink_id]
        receipt = exporter.persisted_receipt(manifest.manifest_id, sink_id)
        if receipt and receipt.get("digest") == manifest.digest() and receipt.get("verified"):
            if not exporter._verify_export(exporter._target(manifest.manifest_id), manifest):
                return {"status": "succeeded", "sink_receipt": receipt}
        return None

    def reconcile_restore(self, source, operation_id):
        if self.restore_target_info is None or self.restore_target_info["restore_mode"] != "isolated_copy":
            return None
        dest = self.restore_target.root.resolve() / (operation_id + ".sqlite")
        expected = source["file_sha256"]
        if dest.is_file() and file_digest(dest) == expected:
            return {"status": "succeeded", "restored_path": str(dest), "file_sha256": expected,
                "mode": "isolated_offline_copy", "reconciled": True}
        return None

    def reconcile_backup(self, operation_id):
        if self.backup_root is None:
            return None
        for path in (self.backup_root / operation_id).glob("*.manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if not manifest.get("all_ok"):
                continue
            self._verified_source(manifest)
            return {"status": "succeeded", "object_type": "backup_manifest", "body": manifest}
        return None
