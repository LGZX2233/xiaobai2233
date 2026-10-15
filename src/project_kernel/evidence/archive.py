"""Archive manifest + bundle sink export/repair state machine (P05).

Design contract 02 §6 / 03 §1,4,6 / 09 §2:

* ``ArchiveManifest`` is frozen only after the delivery receipt and required
  source flush can be referenced. Its digest covers the manifest body and
  deliberately excludes the shell (sink receipts, leases, timestamps).
* An export writes a real bundle (artifacts re-hashed from the store, manifest
  written, fsync) into ``exports/<manifest_id>`` and publishes it atomically.
  An existing target with the same digest is verified and reused; a different
  digest is never overwritten.
* ``repair`` only re-exports the *same* manifest/digest: it fills missing or
  corrupt exported files from the content-addressed store and never re-runs the
  task, never re-ingests content and never rewrites the manifest.
* Content changes produce a *new* artifact digest, therefore a new manifest
  (``ArchiveManifest.with_artifacts``) while the old manifest and its export
  stay readable.
* ``SinkLedger`` records ``pending -> running -> succeeded/failed/unknown`` per
  (manifest, sink) and ``archive_status`` reports acceptance, source flush and
  per-sink state separately from the overall completeness.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..contracts import sha256_digest
from ..contracts.dto import ArtifactRef
from ..contracts.enums import ArchiveOverall, ArchiveSinkState
from ..contracts.errors import (
    KernelError,
    artifact_digest_mismatch,
    invalid_input,
    permission_denied,
)

_READ_CHUNK = 65536

SINK_PENDING = ArchiveSinkState.PENDING.value
SINK_RUNNING = ArchiveSinkState.RUNNING.value
SINK_SUCCEEDED = ArchiveSinkState.SUCCEEDED.value
SINK_FAILED = ArchiveSinkState.FAILED.value
SINK_UNKNOWN = ArchiveSinkState.UNKNOWN.value

ACCEPTED = "accepted"
ACCEPTANCE_PENDING = "pending"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _fsync_file(path: Path) -> None:
    with open(path, "rb+") as f:
        f.flush()
        os.fsync(f.fileno())


def derive_manifest_id(snapshot_digest: str, artifacts: Iterable[ArtifactRef],
                       delivery_operation_refs: Iterable[str],
                       required_sinks: Iterable[str]) -> str:
    """Deterministic manifest id from manifest content (never from its own digest)."""
    material = {
        "snapshot_digest": snapshot_digest,
        "artifacts": sorted((a.to_dict() for a in artifacts), key=lambda a: a["artifact_id"]),
        "delivery_operation_refs": sorted(delivery_operation_refs),
        "required_sinks": sorted(required_sinks),
    }
    return "archive-" + sha256_digest(material)[:16]


@dataclass(frozen=True)
class ArchiveManifest:
    manifest_id: str
    snapshot_digest: str
    delivery_operation_refs: tuple[str, ...]
    artifacts: tuple[ArtifactRef, ...]
    required_sinks: tuple[str, ...]
    schema_version: str = "1.0.0"
    canonicalization: str = "rfc8785"

    def body(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "canonicalization": self.canonicalization,
            "manifest_id": self.manifest_id,
            "snapshot_digest": self.snapshot_digest,
            "delivery_operation_refs": list(self.delivery_operation_refs),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "required_sinks": list(self.required_sinks),
        }

    def digest(self) -> str:
        return sha256_digest(self.body())

    def with_artifacts(self, artifacts: Iterable[ArtifactRef], *,
                       delivery_operation_refs: Iterable[str] | None = None,
                       required_sinks: Iterable[str] | None = None,
                       snapshot_digest: str | None = None) -> "ArchiveManifest":
        """Derive a new manifest for changed content, keeping this one intact."""
        refs = tuple(artifacts)
        operations = (tuple(delivery_operation_refs) if delivery_operation_refs is not None
                      else self.delivery_operation_refs)
        sinks = tuple(required_sinks) if required_sinks is not None else self.required_sinks
        snapshot = snapshot_digest if snapshot_digest is not None else self.snapshot_digest
        return ArchiveManifest(
            manifest_id=derive_manifest_id(snapshot, refs, operations, sinks),
            snapshot_digest=snapshot, delivery_operation_refs=operations, artifacts=refs,
            required_sinks=sinks, schema_version=self.schema_version,
            canonicalization=self.canonicalization)


@dataclass(frozen=True)
class SinkReceipt:
    """A sink export/repair receipt (design 09: succeeded/failed/unknown, digest)."""

    manifest_id: str
    sink_id: str
    state: str  # succeeded / failed / unknown
    digest: str
    locator: str | None = None
    error: str | None = None
    attempts: int = 1
    lease_token: str | None = None
    original_effect_id: str | None = None
    verified: bool = False
    problems: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"manifest_id": self.manifest_id, "sink_id": self.sink_id,
                             "state": self.state, "digest": self.digest,
                             "attempts": self.attempts, "verified": self.verified}
        if self.locator is not None:
            d["locator"] = self.locator
        if self.error is not None:
            d["error"] = self.error
        if self.lease_token is not None:
            d["lease_token"] = self.lease_token
        if self.original_effect_id is not None:
            d["original_effect_id"] = self.original_effect_id
        if self.problems:
            d["problems"] = list(self.problems)
        return d


@dataclass
class SinkLedger:
    """In-memory sink state machine: pending -> running -> terminal state."""

    _entries: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def begin(self, manifest_id: str, sink_id: str,
              lease_token: str | None = None) -> dict[str, Any]:
        entry = self._entries.setdefault(
            (manifest_id, sink_id), {"state": SINK_PENDING, "attempts": 0})  # type: ignore[arg-type]
        entry["state"] = SINK_RUNNING
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        if lease_token is not None:
            entry["lease_token"] = lease_token
        return dict(entry)

    def settle(self, receipt: SinkReceipt) -> None:
        if receipt.state not in (SINK_SUCCEEDED, SINK_FAILED, SINK_UNKNOWN):
            raise KernelError(invalid_input(f"terminal sink state required, got {receipt.state!r}"))
        entry = self._entries.setdefault(
            (receipt.manifest_id, receipt.sink_id),
            {"state": SINK_PENDING, "attempts": 0})  # type: ignore[arg-type]
        entry["state"] = receipt.state
        entry["attempts"] = max(int(entry.get("attempts", 0)), receipt.attempts)
        entry["digest"] = receipt.digest
        entry["receipt"] = receipt.to_dict()
        return None

    def state(self, manifest_id: str, sink_id: str) -> str:
        entry = self._entries.get((manifest_id, sink_id))
        return str(entry["state"]) if entry else SINK_PENDING

    def states(self, manifest_id: str) -> dict[str, str]:
        return {sink: str(entry["state"])
                for (mid, sink), entry in self._entries.items() if mid == manifest_id}

    def entries(self, manifest_id: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for (mid, sink), entry in self._entries.items():
            if manifest_id is None or mid == manifest_id:
                out.append({"manifest_id": mid, "sink_id": sink, **entry})
        return out


def archive_status(manifest: ArchiveManifest, *,
                   sink_states: Mapping[str, str] | None = None,
                   acceptance: str = ACCEPTANCE_PENDING,
                   source_flushed: bool = False,
                   artifacts_ready: bool = True,
                   ledger: SinkLedger | None = None,
                   receipt_store: "SinkReceiptStore | None" = None) -> dict[str, Any]:
    """Report acceptance, source flush and sink completeness separately.

    ``overall`` is ``export_pending`` while no required sink has succeeded,
    ``complete`` only when every required sink succeeded *and* the main facts
    are accepted *and* the required source flush is confirmed *and* the required
    artifacts are ready, else ``partial``.
    """
    states = dict(sink_states or {})
    if receipt_store is not None:
        states.update(receipt_store.states(manifest.manifest_id))
    if ledger is not None:
        states.update(ledger.states(manifest.manifest_id))
    required = list(manifest.required_sinks)
    succeeded = [s for s in required if states.get(s) == SINK_SUCCEEDED]
    if not required:
        overall = ArchiveOverall.PARTIAL.value
    elif not succeeded:
        overall = ArchiveOverall.EXPORT_PENDING.value
    elif (len(succeeded) == len(required) and source_flushed and acceptance == ACCEPTED
          and artifacts_ready):
        overall = ArchiveOverall.COMPLETE.value
    else:
        overall = ArchiveOverall.PARTIAL.value
    return {
        "manifest_id": manifest.manifest_id,
        "manifest_digest": manifest.digest(),
        "acceptance": acceptance,
        "flush": "confirmed" if source_flushed else ACCEPTANCE_PENDING,
        "artifacts": "ready" if artifacts_ready else "not_ready",
        "sinks": {s: states.get(s, SINK_PENDING) for s in required},
        "overall": overall,
    }


class SinkReceiptStore:
    """Durable sink receipts (JSON per manifest/sink) so state survives restarts.

    The DB ``sink_receipt`` table is owned by P01; this filesystem store is the
    P05-side record used for repair and for P06 ``archive.status``.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, manifest_id: str, sink_id: str) -> Path:
        return self.root / manifest_id / f"{sink_id}.json"

    def record(self, receipt: SinkReceipt) -> Path:
        path = self._path(receipt.manifest_id, receipt.sink_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
        tmp.write_text(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        _fsync_file(tmp)
        os.replace(tmp, path)
        return path

    def read(self, manifest_id: str, sink_id: str) -> dict[str, Any] | None:
        path = self._path(manifest_id, sink_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def entries(self, manifest_id: str) -> dict[str, dict[str, Any]]:
        directory = self.root / manifest_id
        if not directory.is_dir():
            return {}
        return {p.stem: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(directory.glob("*.json"))}

    def states(self, manifest_id: str) -> dict[str, str]:
        return {sink: str(entry.get("state", SINK_PENDING))
                for sink, entry in self.entries(manifest_id).items()}


class BundleExporter:
    """Exports a manifest + its artifacts into ``exports/<manifest_id>`` atomically."""

    QUARANTINE_DIR = "_quarantine"

    def __init__(self, exports_root: Path, artifact_store: Any, *,
                 ledger: SinkLedger | None = None,
                 receipt_store: SinkReceiptStore | None = None,
                 allowed_sinks: Iterable[str] | None = None):
        self.exports_root = Path(exports_root)
        self.exports_root.mkdir(parents=True, exist_ok=True)
        self.artifact_store = artifact_store
        self.ledger = ledger if ledger is not None else SinkLedger()
        self.receipt_store = (receipt_store if receipt_store is not None
                              else SinkReceiptStore(self.exports_root / "_receipts"))
        self.allowed_sinks = frozenset(allowed_sinks) if allowed_sinks is not None else None

    def _check_sink(self, sink_id: str) -> None:
        if self.allowed_sinks is not None and sink_id not in self.allowed_sinks:
            raise KernelError(permission_denied(
                f"sink {sink_id!r} is not in the project's configured output range"))

    def sink_states(self, manifest_id: str) -> dict[str, str]:
        """Merged sink states from the durable receipts and the current ledger."""
        states = self.receipt_store.states(manifest_id)
        states.update(self.ledger.states(manifest_id))
        return states

    def persisted_receipt(self, manifest_id: str, sink_id: str) -> dict[str, Any] | None:
        return self.receipt_store.read(manifest_id, sink_id)

    # -- paths -------------------------------------------------------------
    def _target(self, manifest_id: str) -> Path:
        return self.exports_root / manifest_id

    def _artifact_path(self, target: Path, ref: ArtifactRef) -> Path:
        return target / "artifacts" / ref.sha256

    def _read_manifest_digest(self, target: Path) -> str | None:
        p = target / "manifest.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return sha256_digest(data)

    # -- export ------------------------------------------------------------
    def export(self, manifest: ArchiveManifest, sink_id: str, *,
               lease_token: str | None = None, original_effect_id: str | None = None,
               attempt: int = 1) -> SinkReceipt:
        self._check_sink(sink_id)
        digest = manifest.digest()
        self.ledger.begin(manifest.manifest_id, sink_id, lease_token=lease_token)
        target = self._target(manifest.manifest_id)

        if target.exists():
            existing = self._read_manifest_digest(target)
            if existing != digest:
                self._record(SinkReceipt(
                    manifest.manifest_id, sink_id, SINK_FAILED, digest, locator=str(target),
                    error="target holds a different manifest digest; refusing to overwrite",
                    attempts=attempt, lease_token=lease_token,
                    original_effect_id=original_effect_id))
                raise KernelError(artifact_digest_mismatch(
                    f"exports/{manifest.manifest_id} already holds a different manifest"))
            # same manifest/digest -> idempotent: verify, fill any missing file, reuse
            problems = self._verify_export(target, manifest)
            if problems:
                self._fill_missing(target, manifest, problems)
                problems = self._verify_export(target, manifest)
            return self._settle(manifest, sink_id, digest, target, problems,
                                lease_token=lease_token,
                                original_effect_id=original_effect_id, attempt=attempt)

        tmp = self.exports_root / f"{manifest.manifest_id}.tmp-{uuid.uuid4().hex}"
        try:
            (tmp / "artifacts").mkdir(parents=True, exist_ok=True)
            for ref in manifest.artifacts:
                data = self.artifact_store.open_read(ref)  # verifies source bytes
                dest = tmp / "artifacts" / ref.sha256
                with open(dest, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
            (tmp / "manifest.json").write_text(
                json.dumps(manifest.body(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            _fsync_file(tmp / "manifest.json")
            os.replace(tmp, target)  # atomic directory publish, target was absent
        except Exception as exc:  # noqa: BLE001 - report a real sink failure
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            receipt = SinkReceipt(manifest.manifest_id, sink_id, SINK_FAILED, digest,
                                  error=str(exc), attempts=attempt, lease_token=lease_token,
                                  original_effect_id=original_effect_id)
            self._record(receipt)
            return receipt

        problems = self._verify_export(target, manifest)
        return self._settle(manifest, sink_id, digest, target, problems,
                            lease_token=lease_token, original_effect_id=original_effect_id,
                            attempt=attempt)

    # -- repair ------------------------------------------------------------
    def repair(self, manifest: ArchiveManifest, sink_id: str, *,
               original_effect_id: str | None = None, lease_token: str | None = None,
               attempt: int = 2) -> SinkReceipt:
        """Re-export the same manifest/digest; never re-runs the task or a tool.

        Only missing/corrupt exported files are refilled from the
        content-addressed store, and only when their digest matches the frozen
        manifest. The manifest body on disk is never rewritten.
        """
        target = self._target(manifest.manifest_id)
        if not target.exists():
            return self.export(manifest, sink_id, lease_token=lease_token,
                               original_effect_id=original_effect_id, attempt=attempt)
        self._check_sink(sink_id)
        digest = manifest.digest()
        existing = self._read_manifest_digest(target)
        if existing != digest:
            raise KernelError(artifact_digest_mismatch(
                f"repair only re-exports the same manifest/digest;"
                f" exports/{manifest.manifest_id} holds {str(existing)[:12]}…"))
        self.ledger.begin(manifest.manifest_id, sink_id, lease_token=lease_token)
        problems = self._verify_export(target, manifest)
        if problems:
            self._fill_missing(target, manifest, problems)
            problems = self._verify_export(target, manifest)
        return self._settle(manifest, sink_id, digest, target, problems,
                            lease_token=lease_token, original_effect_id=original_effect_id,
                            attempt=attempt)

    # -- verification helpers ---------------------------------------------
    def _verify_export(self, target: Path, manifest: ArchiveManifest) -> list[str]:
        problems: list[str] = []
        if not target.is_dir():
            return [f"target {target} is not a directory"]
        try:
            on_disk = self._read_manifest_digest(target)
        except (OSError, ValueError) as exc:
            return [f"exported manifest.json unreadable: {exc}"]
        if on_disk is None:
            problems.append("exported manifest.json missing")
        elif on_disk != manifest.digest():
            problems.append(f"exported manifest digest {on_disk[:12]}… != {manifest.digest()[:12]}…")
        for ref in manifest.artifacts:
            dest = self._artifact_path(target, ref)
            if not dest.is_file():
                problems.append(f"artifact:{ref.sha256}:missing")
            elif _sha256_file(dest) != ref.sha256:
                problems.append(f"artifact:{ref.sha256}:digest_mismatch")
        return problems

    def _fill_missing(self, target: Path, manifest: ArchiveManifest,
                      problems: list[str]) -> int:
        """Copy artifacts (matching the frozen digests) back into the export."""
        wanted = {ref.sha256: ref for ref in manifest.artifacts}
        filled = 0
        for problem in problems:
            if not problem.startswith("artifact:"):
                continue
            _, digest, reason = problem.split(":", 2)
            ref = wanted.get(digest)
            if ref is None:
                continue
            dest = self._artifact_path(target, ref)
            if dest.exists():
                self._quarantine_export(dest, digest)
            data = self.artifact_store.open_read(ref)  # verifies the store bytes
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if _sha256_file(dest) != ref.sha256:
                raise KernelError(artifact_digest_mismatch(
                    f"repaired copy for {digest[:12]}… does not hash"))
            filled += 1
        return filled

    def _quarantine_export(self, path: Path, digest: str) -> str:
        root = self.exports_root / self.QUARANTINE_DIR
        root.mkdir(parents=True, exist_ok=True)
        dest = root / f"{digest}.{uuid.uuid4().hex[:8]}"
        shutil.move(str(path), str(dest))
        return str(dest)

    def _record(self, receipt: SinkReceipt) -> SinkReceipt:
        """Settle the in-memory ledger and persist the durable sink receipt."""
        self.ledger.settle(receipt)
        self.receipt_store.record(receipt)
        return receipt

    def _settle(self, manifest: ArchiveManifest, sink_id: str, digest: str, target: Path,
                problems: list[str], *, lease_token: str | None,
                original_effect_id: str | None, attempt: int) -> SinkReceipt:
        verified = not problems
        receipt = SinkReceipt(
            manifest.manifest_id, sink_id,
            SINK_SUCCEEDED if verified else SINK_FAILED, digest,
            locator=str(target),
            error=None if verified else "export verification failed",
            attempts=attempt, lease_token=lease_token,
            original_effect_id=original_effect_id, verified=verified,
            problems=tuple(problems))
        return self._record(receipt)
