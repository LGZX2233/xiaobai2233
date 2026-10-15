"""Frozen contract bundle digest (G0). Any contract change must be an explicit
ChangeRequest through P00 and will change this digest; update it deliberately."""
from __future__ import annotations

import json
from pathlib import Path

from project_kernel.contracts import compute_bundle_digest

V1 = Path(__file__).resolve().parents[2] / "contracts" / "v1"

# Frozen at G0 on 2026-10-08.
FROZEN_BUNDLE_DIGEST = "d5fe5816356b0731e78790e997857ea18668cbec16f68673da1f433da07c97cc"


def test_bundle_digest_is_frozen():
    assert compute_bundle_digest() == FROZEN_BUNDLE_DIGEST


def test_bundle_manifest_lists_every_schema_file():
    with open(V1 / "bundle-manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["canonicalization"] == "rfc8785"
    schema_files = {p.name for p in V1.glob("*.schema.json")}
    assert schema_files <= set(manifest["files"])
    assert len(manifest["files"]) >= len(schema_files)
