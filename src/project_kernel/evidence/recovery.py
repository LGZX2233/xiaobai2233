"""Controlled offline restore after all kernel writers release their leases.

This maintenance entry is limited to explicitly configured test project roots.
Human authorization is read from the existing project ledger. Receipts, rollback
history and restore audit live outside the DB being replaced. Ordinary RPC calls
never replace their own active store.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil

from ..contracts import sha256_digest
from ..contracts.errors import KernelError, invalid_input, permission_denied, artifact_digest_mismatch, temporary_unavailable
from ..data.store.access_fence import ProjectAccessFence
from ..data.store.store import Store
from .backup import backup_create, verify_backup_file


def _hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _save_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True)
class ControlledStoreRestoreTarget:
    live_path: Path
    target_id: str


class ControlledStoreRecovery:
    def __init__(self, target, *, project_id, store_id, backup_root, audit_root, artifact_storage, authorize_restore):
        self.target = target
        self.project_id = project_id
        self.store_id = store_id
        self.backup_root = Path(backup_root).resolve()
        self.audit_root = Path(audit_root).resolve()
        self.storage = artifact_storage
        self.authorize_restore = authorize_restore

    def _verify(self, path, source_conn=None):
        checks = verify_backup_file(path, artifact_store=self.storage, source_conn=source_conn)
        if not all(checks[k] for k in ("integrity_ok","foreign_keys_ok","versions_ok","references_ok","artifacts_ok")):
            raise KernelError(invalid_input("restore image verification failed"))
        return checks

    def apply(self, scope, payload, idempotency_key):
        if (scope.project_id != self.project_id or scope.store_id != self.store_id
                or scope.mode != "test" or "project.admin" not in scope.capabilities):
            raise KernelError(permission_denied("offline maintenance requires the configured test project administrator"))
        live = Path(self.target.live_path).resolve()
        operation_id = "recovery-" + sha256_digest({"project":self.project_id,"store":self.store_id,
            "target":str(live),"principal":scope.principal_id,"key":idempotency_key})[:24]
        digest = sha256_digest(payload)
        directory = self.audit_root / operation_id
        receipt_path = directory / "receipt.json"
        with ProjectAccessFence(live, exclusive=True):
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if receipt["input_hash"] != digest:
                    raise KernelError(invalid_input("recovery idempotency key has a different payload"))
                return receipt
            if directory.exists():
                raise KernelError(temporary_unavailable("recovery has an unfinished audit; inspect it without replaying replacement"))
            store = Store.open_project(live, self.project_id, self.store_id, read_only=True)
            try:
                plan, source, target = self.authorize_restore(store,payload)
                if plan["restore_kind"] != "disaster_recovery":
                    raise KernelError(invalid_input("offline maintenance requires a disaster-recovery plan"))
                if (target.get("target_id") != self.target.target_id or target.get("live_path") != str(live)
                        or target.get("restore_mode") != "controlled_replacement"):
                    raise KernelError(permission_denied("approved restore target does not match controlled project path"))
                source_path = Path(source["backup_path"]).resolve()
                if (not source_path.is_relative_to(self.backup_root) or source.get("store_id") != self.store_id
                        or _hash(source_path) != source["file_sha256"]):
                    raise KernelError(artifact_digest_mismatch("backup path, store or digest differs"))
                self._verify(source_path, store.conn)
                directory.mkdir(parents=True, exist_ok=False)
                _save_new(directory / "intent.json", {"operation_id":operation_id,"input_hash":digest,
                    "payload":payload,"plan":plan,"backup":source,"target":target,
                    "scope":{"project_id":scope.project_id,"store_id":scope.store_id,"principal_id":scope.principal_id},
                    "writer_fence":"exclusive SQLite coordinator lease"})
                history = backup_create(store, directory / "history", artifact_store=self.storage)
                if not history.all_ok:
                    raise KernelError(invalid_input("pre-restore history backup failed verification"))
            finally:
                store.close()
            _save_new(directory / "history.json", history.body())
            stage = live.with_name(live.name + "." + operation_id + ".stage")
            original = directory / "original.sqlite"
            # Sidecars move with the original DB so post-snapshot WAL facts survive.
            moved = []
            try:
                with source_path.open("rb") as inp, stage.open("xb") as out:
                    shutil.copyfileobj(inp, out)
                    out.flush()
                    os.fsync(out.fileno())
                if _hash(stage) != source["file_sha256"]:
                    raise KernelError(artifact_digest_mismatch("staged restore digest differs"))
                self._verify(stage)
                live.rename(original)
                for suffix in ("-wal","-shm","-journal"):
                    sidecar = live.with_name(live.name + suffix)
                    if sidecar.exists():
                        saved = original.with_name(original.name + suffix)
                        sidecar.rename(saved)
                        moved.append((saved,sidecar))
                stage.rename(live)
                if _hash(live) != source["file_sha256"]:
                    raise KernelError(artifact_digest_mismatch("published restore digest differs"))
                checks = self._verify(live)
                receipt = {"operation_id":operation_id,"status":"succeeded","input_hash":digest,
                    "mode":"controlled_test_store_replacement","restored_path":str(live),
                    "file_sha256":source["file_sha256"],"checks":checks,"writer_fence_held":True,
                    "history_backup":history.body(),"original_path":str(original),"audit_path":str(directory)}
                receipt = json.loads(json.dumps(receipt))
                _save_new(receipt_path, receipt)
                return receipt
            except Exception as exc:
                if original.exists():
                    if live.exists():
                        live.rename(directory / "failed-restored.sqlite")
                    original.rename(live)
                    for saved,sidecar in moved:
                        saved.rename(sidecar)
                _save_new(directory / "failure.json", {"type":type(exc).__name__,"message":str(exc),
                    "rollback_preserved":str(live),"manual_reconciliation_required":True})
                raise

    def reconcile(self, scope, payload, idempotency_key):
        """Inspect a lost receipt; never repeat a database replacement."""
        if (scope.project_id != self.project_id or scope.store_id != self.store_id
                or scope.mode != "test" or "project.admin" not in scope.capabilities):
            raise KernelError(permission_denied("offline reconciliation requires project administration"))
        live = Path(self.target.live_path).resolve()
        oid = "recovery-" + sha256_digest({"project":self.project_id,"store":self.store_id,
            "target":str(live),"principal":scope.principal_id,"key":idempotency_key})[:24]
        directory = self.audit_root / oid
        with ProjectAccessFence(live, exclusive=True):
            intent = json.loads((directory / "intent.json").read_text(encoding="utf-8"))
            if intent["input_hash"] != sha256_digest(payload):
                raise KernelError(invalid_input("recovery reconciliation payload differs"))
            receipt_path = directory / "receipt.json"
            if receipt_path.exists():
                return json.loads(receipt_path.read_text(encoding="utf-8"))
            if (directory / "failure.json").exists():
                return {"operation_id":oid,"status":"failed","audit_path":str(directory)}
            history_path = directory / "history.json"
            original = directory / "original.sqlite"
            if (live.exists() and original.exists() and history_path.exists()
                    and _hash(live) == intent["backup"]["file_sha256"]):
                receipt = {"operation_id":oid,"status":"succeeded","input_hash":intent["input_hash"],
                    "mode":"controlled_test_store_replacement","restored_path":str(live),
                    "file_sha256":intent["backup"]["file_sha256"],"checks":self._verify(live),
                    "writer_fence_held":True,"reconciled":True,
                    "history_backup":json.loads(history_path.read_text(encoding="utf-8")),
                    "original_path":str(original),"audit_path":str(directory)}
                receipt = json.loads(json.dumps(receipt))
                _save_new(receipt_path,receipt)
                return receipt
            return {"operation_id":oid,"status":"unknown","audit_path":str(directory)}
