"""RFC8785 (JCS) canonicalization + SHA-256 digests.

Digest rules (design D13 / 04 §7): JCS (RFC8785) with UTF-8, no BOM, SHA-256
lowercase hex. NaN/Infinity are forbidden; strings are not trimmed or Unicode
normalized; arrays with semantic order are never sorted. Amounts and large
integers travel as strings. The bundle digest is JCS over a stable manifest of
the frozen contract files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jcs

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts" / "v1"


def canonicalize(value: Any) -> bytes:
    """RFC8785 canonical UTF-8 bytes of *value*."""
    # jcs rejects NaN/Infinity and sorts object keys per RFC8785.
    return jcs.canonicalize(value)


def digest_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_digest(value: Any) -> str:
    """SHA-256 of the RFC8785 canonical form of *value*."""
    return digest_of_bytes(canonicalize(value))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema_files() -> list[Path]:
    files = sorted(p for p in CONTRACTS_DIR.glob("*.json") if p.name != "bundle-manifest.json")
    return files


def build_bundle_manifest() -> dict[str, Any]:
    """A canonical manifest {schema_version, files: {relpath: sha256}}."""
    files = {p.name: sha256_file(p) for p in _schema_files()}
    return {
        "schema_version": "1.0.0",
        "canonicalization": "rfc8785",
        "files": files,
    }


def compute_bundle_digest() -> str:
    """The frozen contract bundle digest: JCS(build_bundle_manifest()) -> SHA-256."""
    return sha256_digest(build_bundle_manifest())


def write_bundle_manifest() -> str:
    manifest = build_bundle_manifest()
    digest = sha256_digest(manifest)
    out = CONTRACTS_DIR / "bundle-manifest.json"
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return digest
