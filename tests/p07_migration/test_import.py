"""Acceptance #2/#3/#4: idempotent rerun, cross-scope isolation, no fabrication."""
from __future__ import annotations

import json

from project_kernel.migration.legacy import LegacyImportService

from .helpers import PROJECT_MAPPING, count, make_legacy_source, make_store


def _rows(store, sql, *args):
    return store.conn.execute(sql, args).fetchall()


def test_rerun_adds_no_revision_or_event(tmp_path):
    source = make_legacy_source(tmp_path)
    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")

    r1 = svc.import_batch()
    assert r1.imported > 0
    before = {
        "revision": count("revision", store),
        "entity": count("entity", store),
        "commit_log": _rows(store, "SELECT COUNT(*) FROM commit_log")[0][0],
        "audit": _rows(store, "SELECT COUNT(*) FROM audit_event")[0][0],
        "receipt": _rows(store, "SELECT COUNT(*) FROM command_receipt")[0][0],
    }

    r2 = svc.import_batch()
    assert r2.imported == 0
    assert r2.skipped_existing == r1.imported
    after = {
        "revision": count("revision", store),
        "entity": count("entity", store),
        "commit_log": _rows(store, "SELECT COUNT(*) FROM commit_log")[0][0],
        "audit": _rows(store, "SELECT COUNT(*) FROM audit_event")[0][0],
        "receipt": _rows(store, "SELECT COUNT(*) FROM command_receipt")[0][0],
    }
    assert after == before
    store.close()


def test_cross_scope_isolation(tmp_path):
    source = make_legacy_source(tmp_path)
    store_a = make_store(tmp_path, "proj-a", "store-a")
    store_b = make_store(tmp_path, "proj-b", "store-b")

    svc = LegacyImportService(store_a, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    svc.import_batch()

    assert count("revision", store_a) > 0
    # nothing leaks into project B's store
    assert count("revision", store_b, project_id="proj-b") == 0
    assert count("entity", store_b, project_id="proj-b") == 0
    # every imported fact in A carries A's project id (scope stamp)
    wrong = _rows(store_a, "SELECT COUNT(*) FROM revision WHERE project_id != ?", "proj-a")
    assert wrong[0][0] == 0
    store_a.close()
    store_b.close()


def test_no_fabricated_pass_approval_usage_or_causal_parent(tmp_path):
    source = make_legacy_source(tmp_path)
    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    svc.import_batch()

    def fact(legacy_type, legacy_id):
        row = store.conn.execute(
            "SELECT r.payload_json FROM revision r WHERE r.type='imported_fact' AND r.project_id='proj-a'"
            " AND json_extract(r.payload_json, '$.legacy_type')=? "
            " AND json_extract(r.payload_json, '$.legacy_id')=?",
            (legacy_type, legacy_id)).fetchone()
        return json.loads(row[0]) if row else None

    # failed attempts stay failed
    a2 = fact("attempt", "a-2")
    assert a2["raw"]["status"] == "failed"
    assert a2["raw"]["selected"] is False or str(a2["raw"]["selected"]).lower() in ("false", "0")
    # usage only present where the source had it
    a1 = fact("attempt", "a-1")
    assert a1["raw"]["usage_amount"] == "1.25"
    # a-2 had no usage: never fabricate an amount for it
    assert not a2["raw"].get("usage_amount")
    # approvals: only the single source approval, decision preserved
    approvals = _rows(store, "SELECT COUNT(*) FROM revision WHERE type='imported_fact'"
                            " AND json_extract(payload_json, '$.legacy_type')='approval'")
    assert approvals[0][0] == 1
    ap = fact("approval", "ap-1")
    assert ap["raw"]["decision"] == "approved"
    # no causal parent is fabricated in the stored payload
    assert "causal_refs" not in a1 and "causal_refs" not in a2
    store.close()


def test_quarantine_writes_manifest_and_raw_and_repair_plan(tmp_path):
    source = make_legacy_source(tmp_path)
    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    report = svc.import_batch()
    assert report.quarantined > 0
    assert report.quarantine_path is not None

    qdir = tmp_path / "quarantine" / "b1"
    manifest = json.loads((qdir / "quarantine-manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == report.quarantined
    assert manifest["repair_plan"]["actions"]
    # each quarantined item keeps its raw payload in a file
    raw_files = list((qdir / "raw").glob("*.json"))
    assert len(raw_files) == report.quarantined
    store.close()


def test_conflicting_source_digest_is_quarantined_not_silently_skipped(tmp_path):
    source = make_legacy_source(tmp_path)
    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    svc.import_batch()
    before = count("revision", store)

    # mutate the source: same legacy_id t-1 now has different content
    import sqlite3
    db = source / "legacy.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE tasks SET title='Changed title' WHERE legacy_id='t-1'")
    conn.commit()
    conn.close()

    svc2 = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                               "proj-a", PROJECT_MAPPING, batch_id="b2")
    r2 = svc2.import_batch()
    # no new revision for the conflicting record; it is quarantined as duplicate
    assert count("revision", store) == before
    assert r2.by_classification.get("duplicate", 0) >= 1
    store.close()
