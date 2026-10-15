"""Content-addressed artifact storage: staging -> ready, no-overwrite (P05).

Design contract 02 §6 / 09 §2:

* ``stage`` persists bytes under ``staging/<token>`` and returns the declared
  digest/size. The locator is produced by the service, never by a model.
* ``publish`` / ``register`` write a temp file, ``flush`` + ``fsync``, then
  publish with an atomic link into ``sha256/<ab>/<digest>``. An existing
  same-digest file is verified *before* it is reused; different bytes are never
  overwritten -- the corrupt entry is quarantined and reported.
* ``verify`` re-hashes the stored bytes. Corrupt store content is moved under
  ``quarantine/`` and recorded as ``unavailable`` so future use is blocked,
  while the original ``ArtifactRef`` digest is never rewritten.
* ``require_ready`` is the freeze guard: a snapshot may only be frozen while
  every required artifact verifies as ready right now.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..contracts.dto import ArtifactRef, ObjectRef
from ..contracts.errors import (
    KernelError,
    artifact_digest_mismatch,
    artifact_missing,
    invalid_input,
    reference_not_found,
    scope_mismatch,
)

_READ_CHUNK = 65536


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_within(path: Path, root: Path, what: str) -> Path:
    """Reject any locator that escapes the service-owned root."""
    resolved = Path(os.path.abspath(path))
    root_abs = Path(os.path.abspath(root))
    if resolved != root_abs and root_abs not in resolved.parents:
        raise KernelError(invalid_input(f"{what} escapes the artifact root: {path}"))
    return resolved


def locator_of(staged_locator_ref: Any) -> str:
    """Resolve a trusted staged locator from a string or an ObjectRef-like dict.

    Only a locator produced by ``stage`` (or a trusted caller) is accepted; the
    value is still range-checked against the staging root by ``staged_path``.
    """
    if isinstance(staged_locator_ref, str):
        return staged_locator_ref
    if isinstance(staged_locator_ref, dict):
        locator = staged_locator_ref.get("locator")
        if isinstance(locator, str) and locator:
            return locator
        object_type = staged_locator_ref.get("object_type")
        object_id = staged_locator_ref.get("object_id")
        if isinstance(object_type, str) and isinstance(object_id, str):
            return f"{object_type}/{object_id}"
    object_type = getattr(staged_locator_ref, "object_type", None)
    object_id = getattr(staged_locator_ref, "object_id", None)
    if isinstance(object_type, str) and isinstance(object_id, str):
        return f"{object_type}/{object_id}"
    raise KernelError(invalid_input("trusted_staged_locator_ref must carry a locator"))


@dataclass(frozen=True)
class StagedArtifact:
    """A staged (not yet published) artifact; the hash is over the real bytes."""

    staged_locator: str
    sha256: str
    size_bytes: int
    media_type: str = "application/octet-stream"
    retention: str = "default"
    source_ref: dict[str, Any] | None = None
    state: str = "staged"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"staged_locator": self.staged_locator, "sha256": self.sha256,
                            "size_bytes": str(self.size_bytes), "media_type": self.media_type,
                            "retention": self.retention, "state": self.state}
        if self.source_ref is not None:
            d["source_ref"] = self.source_ref
        return d


@dataclass(frozen=True)
class ArtifactLocation:
    """One concrete location of an artifact (design 02: location table)."""

    sink: str
    locator: str
    state: str
    digest: str
    verified_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"sink": self.sink, "locator": self.locator,
                            "state": self.state, "digest": self.digest}
        if self.verified_at is not None:
            d["verified_at"] = self.verified_at
        return d


@dataclass(frozen=True)
class ArtifactRecord:
    """Ready artifact plus its verified location (design 02: artifact table)."""

    artifact_id: str
    sha256: str
    size_bytes: str
    media_type: str
    retention: str
    state: str
    source_ref: dict[str, Any] | None = None
    location: ArtifactLocation | None = None
    reused: bool = False

    def to_ref(self, required: bool = True) -> ArtifactRef:
        return ArtifactRef(artifact_id=self.artifact_id, sha256=self.sha256,
                           size_bytes=self.size_bytes, media_type=self.media_type,
                           required=required)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"artifact_id": self.artifact_id, "sha256": self.sha256,
                            "size_bytes": self.size_bytes, "media_type": self.media_type,
                            "retention": self.retention, "state": self.state,
                            "reused": self.reused}
        if self.source_ref is not None:
            d["source_ref"] = self.source_ref
        if self.location is not None:
            d["location"] = self.location.to_dict()
        return d


class ArtifactStorage:
    """Filesystem content-addressed store rooted at a service-provided path."""

    SINK = "artifact-store"
    _STAGING = "staging"
    _READY = "sha256"
    _QUARANTINE = "quarantine"

    def __init__(self, root: Path, *, quarantine: bool = True):
        self.root = Path(root)
        self.quarantine_enabled = quarantine
        self.staging_root = self.root / self._STAGING
        self.ready_root = self.root / self._READY
        self.quarantine_root = self.root / self._QUARANTINE
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.ready_root.mkdir(parents=True, exist_ok=True)
        self._unavailable: dict[str, dict[str, Any]] = {}

    # -- paths -------------------------------------------------------------
    def _ready_path(self, digest: str) -> Path:
        return self.ready_root / digest[:2] / digest

    def staged_path(self, staged_locator: str) -> Path:
        return _assert_within(self.root / staged_locator, self.staging_root, "staged locator")

    # -- staging -----------------------------------------------------------
    def stage(self, data: bytes, media_type: str = "application/octet-stream",
              retention: str = "default",
              source_ref: dict[str, Any] | None = None) -> StagedArtifact:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise KernelError(invalid_input("stage requires bytes"))
        payload = bytes(data)
        digest = hashlib.sha256(payload).hexdigest()
        token = uuid.uuid4().hex
        path = self.staging_root / token
        with open(path, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        return StagedArtifact(staged_locator=f"{self._STAGING}/{token}", sha256=digest,
                              size_bytes=len(payload), media_type=media_type,
                              retention=retention, source_ref=source_ref)

    def stage_file(self, source: Path, media_type: str = "application/octet-stream",
                   retention: str = "default",
                   source_ref: dict[str, Any] | None = None) -> StagedArtifact:
        """Stage an existing real file without loading it fully into memory."""
        src = Path(source)
        if not src.is_file():
            raise KernelError(artifact_missing(f"source file {src} missing"))
        token = uuid.uuid4().hex
        dest = self.staging_root / token
        digest = hashlib.sha256()
        size = 0
        with open(src, "rb") as r, open(dest, "wb") as w:
            for chunk in iter(lambda: r.read(_READ_CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
                w.write(chunk)
            w.flush()
            os.fsync(w.fileno())
        return StagedArtifact(staged_locator=f"{self._STAGING}/{token}",
                              sha256=digest.hexdigest(), size_bytes=size,
                              media_type=media_type, retention=retention, source_ref=source_ref)

    # -- publishing --------------------------------------------------------
    def register(self, staged_locator_ref: Any, digest: str, *,
                 source_ref: dict[str, Any] | None = None,
                 media_type: str = "application/octet-stream",
                 retention: str = "default") -> ArtifactRecord:
        """``artifact.register``: trusted staged locator + declared digest -> ready."""
        locator = locator_of(staged_locator_ref)
        return self._publish(locator, digest, media_type, retention, source_ref)

    def publish(self, staged: StagedArtifact, media_type: str | None = None,
                required: bool = True) -> ArtifactRef:
        """Publish a staged artifact and return the ready ``ArtifactRef``."""
        record = self._publish(staged.staged_locator, staged.sha256,
                               media_type or staged.media_type, staged.retention,
                               staged.source_ref)
        return record.to_ref(required)

    def _publish(self, locator: str, declared_digest: str, media_type: str,
                 retention: str, source_ref: dict[str, Any] | None) -> ArtifactRecord:
        path = self.staged_path(locator)
        if not path.is_file():
            raise KernelError(artifact_missing(f"staged file {locator} missing"))
        actual = _sha256_file(path)
        if actual != declared_digest:
            # bytes changed after the digest was computed: never mark ready
            raise KernelError(artifact_digest_mismatch(
                f"staged {locator} hashes {actual[:12]}… but declared"
                f" {declared_digest[:12]}…; not published"))
        size = path.stat().st_size
        target = self._ready_path(declared_digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        reused = False
        if target.exists():
            existing = _sha256_file(target)
            if existing != declared_digest:
                quarantined = self._isolate(target, "digest_mismatch", declared_digest)
                raise KernelError(artifact_digest_mismatch(
                    f"content-addressed store holds different bytes for"
                    f" {declared_digest[:12]}…; corrupt entry isolated at"
                    f" {quarantined}; refused to overwrite"))
            reused = True
        else:
            self._atomic_publish(path, target, declared_digest)
        # verify the published bytes before the artifact is ever reported ready
        published = _sha256_file(target)
        if published != declared_digest:
            quarantined = self._isolate(target, "post_publish_mismatch", declared_digest)
            raise KernelError(artifact_digest_mismatch(
                f"published bytes for {declared_digest[:12]}… do not verify; isolated at"
                f" {quarantined}"))
        if target.stat().st_size != size:
            raise KernelError(artifact_digest_mismatch(
                f"published size for {declared_digest[:12]}… differs from staged bytes"))
        return ArtifactRecord(
            artifact_id=declared_digest, sha256=declared_digest, size_bytes=str(size),
            media_type=media_type, retention=retention, state="ready",
            source_ref=source_ref,
            location=ArtifactLocation(sink=self.SINK, locator=str(target), state="ready",
                                      digest=declared_digest, verified_at=_utc_now()),
            reused=reused)

    def _atomic_publish(self, source: Path, target: Path, digest: str) -> None:
        tmp = target.with_name(f".{digest}.tmp-{uuid.uuid4().hex}")
        try:
            with open(source, "rb") as r, open(tmp, "wb") as w:
                shutil.copyfileobj(r, w, _READ_CHUNK)
                w.flush()
                os.fsync(w.fileno())
            if _sha256_file(tmp) != digest:
                raise KernelError(artifact_digest_mismatch("temporary copy does not hash"))
            try:
                os.link(tmp, target)  # atomic, refuses to overwrite
            except FileExistsError:
                if _sha256_file(target) != digest:
                    raise KernelError(artifact_digest_mismatch("concurrent publish differs"))
        finally:
            if tmp.exists():
                tmp.unlink()

    # -- verification ------------------------------------------------------
    def verify(self, ref: ArtifactRef, *, isolate: bool = True) -> dict[str, Any]:
        path = self._ready_path(ref.sha256)
        if not path.is_file():
            return {"ok": False, "reason": "missing", "state": "missing"}
        actual = _sha256_file(path)
        if actual != ref.sha256:
            quarantined = self._isolate(path, "digest_mismatch", ref.sha256) if isolate else None
            return {"ok": False, "reason": "digest_mismatch", "state": "unavailable",
                    "quarantined": quarantined}
        size = path.stat().st_size
        if str(size) != ref.size_bytes:
            return {"ok": False, "reason": "size_mismatch", "state": "unavailable"}
        return {"ok": True, "reason": None, "state": "ready", "path": str(path),
                "sha256": actual, "size_bytes": str(size)}

    def open_read(self, ref: ArtifactRef) -> bytes:
        v = self.verify(ref)
        if not v["ok"]:
            raise KernelError(artifact_missing(
                f"artifact {ref.artifact_id} is {v['reason']} ({v['state']})"))
        return Path(v["path"]).read_bytes()

    def require_ready(self, refs: Iterable[ArtifactRef]) -> tuple[ArtifactRef, ...]:
        """Freeze guard: every required artifact must verify as ready right now."""
        refs = tuple(refs)
        problems: list[dict[str, Any]] = []
        for ref in refs:
            v = self.verify(ref)
            if not v["ok"]:
                problems.append({"artifact_id": ref.artifact_id, "sha256": ref.sha256,
                                 "reason": v["reason"], "state": v["state"]})
        if problems:
            detail = json.dumps(problems, ensure_ascii=False, separators=(",", ":"))
            if any(p["reason"] == "missing" for p in problems):
                raise KernelError(artifact_missing(f"required artifact not ready: {detail}"))
            raise KernelError(artifact_digest_mismatch(f"required artifact not ready: {detail}"))
        return refs

    # -- quarantine --------------------------------------------------------
    def _isolate(self, path: Path, reason: str, digest: str) -> str | None:
        """Move corrupt store content aside and record it unavailable.

        If quarantine is disabled the corrupt file is left untouched (callers
        still get the failure); nothing is ever overwritten in place.
        """
        if not self.quarantine_enabled:
            return None
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        dest = self.quarantine_root / f"{digest}.{uuid.uuid4().hex[:8]}.{reason}"
        try:
            os.replace(path, dest)
        except OSError:
            shutil.copy2(path, dest)
            try:
                path.unlink()
            except OSError:
                pass
        entry = {"sha256": digest, "reason": reason, "state": "unavailable",
                 "isolated_at": _utc_now(), "original_path": str(path),
                 "quarantine_path": str(dest)}
        with open(self.quarantine_root / "index.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._unavailable[digest] = entry
        return str(dest)

    def unavailable(self) -> dict[str, dict[str, Any]]:
        """Artifacts found corrupt in this process, keyed by digest."""
        return dict(self._unavailable)

    def quarantine_entries(self) -> list[dict[str, Any]]:
        index = self.quarantine_root / "index.jsonl"
        if not index.is_file():
            return []
        entries: list[dict[str, Any]] = []
        for line in index.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries


class ScopedArtifactStorage:
    """Binds the scope-free ``ArtifactStorage`` to the typed ``ArtifactPort`` surface.

    ``ports.ArtifactPort`` (design 09 §2) takes a ``ResolvedScope``: locators and
    paths still come from the service, and every call re-checks the scope's
    project before touching the store. ``trusted_stream`` is bytes or a real
    file path; ``staged_ref`` / ``artifact_ref`` are ObjectRefs whose
    ``object_id`` carries the staging token / artifact digest, exactly as the
    ``artifact.register`` payload defines a trusted locator ref.
    """

    def __init__(self, storage: ArtifactStorage, *, project_id: str):
        self.storage = storage
        self.project_id = project_id
        self._references: dict[str, ArtifactRef] = {}

    # -- scope -------------------------------------------------------------
    def _require_scope(self, scope: Any) -> None:
        project_id = getattr(scope, "project_id", None)
        if project_id is None and isinstance(scope, dict):
            project_id = scope.get("project_id")
        if project_id != self.project_id:
            raise KernelError(scope_mismatch(
                f"artifact scope project {project_id!r} != store project {self.project_id!r}"))

    @staticmethod
    def _locator(ref: Any) -> str:
        return locator_of(ref)

    # -- port --------------------------------------------------------------
    def stage(self, scope: Any, trusted_stream: Any, source_ref: Any = None,
              media_type: str = "application/octet-stream",
              retention: str = "default") -> StagedArtifact:
        self._require_scope(scope)
        source = source_ref.to_dict() if hasattr(source_ref, "to_dict") else source_ref
        if isinstance(trusted_stream, (bytes, bytearray, memoryview)):
            return self.storage.stage(bytes(trusted_stream), media_type, retention, source)
        return self.storage.stage_file(Path(trusted_stream), media_type, retention, source)

    def staged_ref(self, staged: StagedArtifact) -> ObjectRef:
        return ObjectRef(self.project_id, "staging", staged.staged_locator.split("/")[-1],
                         "staged")

    def register(self, scope: Any, staged_locator_ref: Any, digest: str, *,
                 source_ref: Any = None, media_type: str = "application/octet-stream",
                 retention: str = "default") -> ArtifactRecord:
        self._require_scope(scope)
        source = source_ref.to_dict() if hasattr(source_ref, "to_dict") else source_ref
        record = self.storage.register(staged_locator_ref, digest, source_ref=source,
                                       media_type=media_type, retention=retention)
        self._references[record.artifact_id] = record.to_ref()
        return record

    def publish(self, scope: Any, staged_ref: Any, digest: str,
                source_ref: Any = None) -> ArtifactRef:
        self._require_scope(scope)
        staged = StagedArtifact(staged_locator=self._locator(staged_ref), sha256=digest,
                                size_bytes=0)
        record = self.storage.register(staged.staged_locator, digest,
                                       source_ref=(source_ref.to_dict()
                                                   if hasattr(source_ref, "to_dict")
                                                   else source_ref))
        self._references[record.artifact_id] = record.to_ref()
        return record.to_ref()

    def verify(self, scope: Any, artifact_ref: Any, required: Any = True) -> dict[str, Any]:
        self._require_scope(scope)
        ref = self._ref(artifact_ref)
        result = self.storage.verify(ref)
        if not result["ok"] and required:
            result["required"] = True
        return result

    def open_read(self, scope: Any, artifact_ref: Any) -> bytes:
        self._require_scope(scope)
        return self.storage.open_read(self._ref(artifact_ref))

    def _ref(self, artifact_ref: Any) -> ArtifactRef:
        if isinstance(artifact_ref, ArtifactRef):
            return artifact_ref
        if isinstance(artifact_ref, dict) and "sha256" in artifact_ref:
            return ArtifactRef(artifact_ref["artifact_id"], artifact_ref["sha256"],
                               artifact_ref["size_bytes"], artifact_ref["media_type"],
                               artifact_ref.get("required", True))
        artifact_id = getattr(artifact_ref, "object_id", None)
        if isinstance(artifact_ref, dict):
            artifact_id = artifact_ref.get("object_id")
        known = self._references.get(str(artifact_id))
        if known is None:
            raise KernelError(reference_not_found(
                f"artifact {artifact_id!r} was not published through this port"))
        return known
