"""Acceptance #4: reconciliation report over attempts/approvals/evidence/files."""
from __future__ import annotations

from project_kernel.migration.legacy import LegacyImportService, reconcile
from project_kernel.migration.legacy import LegacyReader

from .helpers import PROJECT_MAPPING, make_legacy_source, make_store


def test_reconcile_reports_failed_unselected_and_preserves_decisions(tmp_path):
    source = make_legacy_source(tmp_path)
    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    svc.import_batch()
    report = svc.reconcile(svc.read_plan())

    assert report.ok is True
    failed = [a for a in report.attempts if a.legacy_id in ("a-2", "a-3")]
    assert failed and all(a.mismatch is None for a in failed)
    unselected = [a for a in report.attempts if a.legacy_id == "a-2"]
    assert unselected and unselected[0].classification == "ok"
    assert report.approvals and report.approvals[0].mismatch is None
    # evidence and file hashes preserved
    assert all(e.mismatch is None for e in report.evidence)
    assert all(f.mismatch is None for f in report.files)
    store.close()


def test_reconcile_detects_fabricated_pass(tmp_path):
    source = make_legacy_source(tmp_path)
    store = make_store(tmp_path)
    svc = LegacyImportService(store, source, tmp_path / "quarantine", "legacy-store",
                              "proj-a", PROJECT_MAPPING, batch_id="b1")
    svc.import_batch()

    # Tamper with the persisted imported fact for a failed attempt: simulate a
    # fabricated pass. Reconcile must flag the mismatch.
    store.conn.execute(
        "UPDATE revision SET payload_json = replace(payload_json, '\"status\":\"failed\"',"
        " '\"status\":\"completed\"') WHERE type='imported_fact'"
        " AND json_extract(payload_json, '$.legacy_id')='a-2'")
    store.conn.commit()

    report = svc.reconcile(svc.read_plan())
    assert report.ok is False
    tampered = [a for a in report.attempts if a.legacy_id == "a-2"]
    assert tampered and tampered[0].mismatch == "failed attempt status was changed during import"
    store.close()


def test_reconcile_direct_call_without_store(tmp_path):
    source = make_legacy_source(tmp_path)
    records = LegacyReader(source, "legacy-store").read()
    from project_kernel.migration.legacy import LegacyMapper
    facts = LegacyMapper("legacy-store", "proj-a", PROJECT_MAPPING).map_all(records)
    report = reconcile("legacy-store", "proj-a", records, facts)
    assert report.source_store_id == "legacy-store"
    assert report.target_project_id == "proj-a"
    assert report.ok is True
