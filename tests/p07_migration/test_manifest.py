"""Acceptance #1/#4: source hash unchanged, schema/count manifest, no write."""
from __future__ import annotations

from project_kernel.migration.legacy import build_source_manifest
from project_kernel.migration.legacy import LegacyImportService

from .helpers import PROJECT_MAPPING, make_legacy_source, make_store


def _snapshot(source):
    from pathlib import Path
    out = {}
    for p in sorted(x for x in Path(source).rglob("*") if x.is_file()):
        out[p.relative_to(source).as_posix()] = p.read_bytes()
    return out


def test_source_bytes_and_hash_unchanged_after_import(tmp_path):
    source = make_legacy_source(tmp_path)
    before = _snapshot(source)
    before_manifest = build_source_manifest(source, "legacy-store")

    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    svc.import_batch()

    after = _snapshot(source)
    assert after == before  # byte-for-byte: no legacy deletion/migration ran
    after_manifest = build_source_manifest(source, "legacy-store")
    assert after_manifest.digest == before_manifest.digest
    store.close()


def test_manifest_records_schema_and_counts(tmp_path):
    source = make_legacy_source(tmp_path)
    manifest = build_source_manifest(source, "legacy-store")

    tables = {t.table: t.count for t in manifest.tables}
    assert tables == {"approvals": 1, "attempts": 4, "evidence": 3, "files": 1,
                      "projects": 2, "tasks": 4}
    # digest is deterministic and excludes shell fields (created_at)
    again = build_source_manifest(source, "legacy-store")
    assert again.digest == manifest.digest
    assert "created_at" not in manifest.body()
    # every file is hashed
    assert manifest.file_hash("legacy.sqlite")
