"""P06 read-model tests: envelope watermarks, as_of consistency, pagination.

Real temporary SQLite only. All fixtures are written through the P01 store/UoW
public API (see helpers.py) so the queries are tested against a real ledger.
"""
from __future__ import annotations

import json

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.data.queries.service import QueryService

from p01_store.helpers import make_store
from p06_queries.helpers import PROJ, add_task, append_revision, ref

ENVELOPE_FIELDS = {"query", "as_of_seq", "projection_version", "computed_at",
                   "source_watermarks", "freshness", "completeness", "gaps",
                   "next_page_token", "data"}


def test_envelope_fields_and_no_source_data_is_not_failure(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        add_task(store, "k1", "task-1")
        env = q.project_overview()
        assert ENVELOPE_FIELDS <= set(env)
        # no source stream registered -> "no data", explicitly not a failure
        assert env["source_watermarks"]["data_state"] == "no_data"
        assert env["completeness"] == "complete"
        assert env["gaps"] == []
        assert env["freshness"]["projection_lag_seq"] == "0"
        assert env["freshness"]["projection_stale"] is False
        # legacy top-level alias kept for P10 callers
        assert env["object_counts"]["task"] == 1
        assert env["data"]["object_counts"]["task"] == 1
    finally:
        store.close()


def test_gapped_source_incomplete_and_unavailable_source_unknown(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        store.conn.execute(
            "INSERT INTO source_cursor (source_stream_key, contiguous_seq, seen_high_water,"
            " gaps_json, status, updated_seq) VALUES (?,?,?,?,?,?)",
            ('["host","session","gen"]', "2", "5", json.dumps([3, 4]), "gapped", 1))
        env = q.project_overview()
        assert env["source_watermarks"]["data_state"] == "gapped"
        assert env["completeness"] == "incomplete"
        assert env["gaps"][0]["source_stream_key"] == '["host","session","gen"]'
        assert env["gaps"][0]["missing"] == [3, 4]
        assert env["source_watermarks"]["streams"][0]["lag"] == "3"

        # An unavailable source must never be merged with "no data".
        store.conn.execute("UPDATE source_cursor SET status='failed', gaps_json='[]'")
        env = q.project_overview()
        assert env["source_watermarks"]["data_state"] == "unavailable"
        assert env["source_watermarks"]["streams"][0]["state"] == "unavailable"
        assert env["completeness"] == "unknown"
        assert env["freshness"]["state"] == "unknown"
    finally:
        store.close()


def test_legacy_delimiter_cursor_is_unavailable_not_trusted(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    try:
        store.conn.execute(
            "INSERT INTO source_cursor (source_stream_key, contiguous_seq, seen_high_water,"
            " gaps_json, status, updated_seq) VALUES (?,?,?,?,?,?)",
            ("a:b:c:1", "2", "2", "[]", "active", 1))
        env = QueryService(store).project_overview()
        assert env["source_watermarks"]["data_state"] == "unavailable"
        assert env["source_watermarks"]["streams"][0]["state"] == "unavailable"
        assert env["completeness"] == "unknown"
    finally:
        store.close()


def test_as_of_watermark_consistency_and_future_watermark_refused(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        add_task(store, "k1", "task-1")
        first = q.project_overview()
        as_of_first = int(first["as_of_seq"])
        add_task(store, "k2", "task-2")

        historical = q.project_overview(as_of_seq=as_of_first)
        assert historical["as_of_seq"] == str(as_of_first)
        assert historical["data"]["object_counts"]["task"] == 1
        assert historical["freshness"]["projection_stale"] is True
        assert historical["freshness"]["projection_lag_seq"] != "0"
        assert historical["completeness"] == "incomplete"

        assert q.project_overview()["data"]["object_counts"]["task"] == 2

        with pytest.raises(KernelError) as exc:
            q.project_overview(as_of_seq=str(int(q.project_overview()["as_of_seq"]) + 10))
        assert exc.value.error.code == "AS_OF_UNAVAILABLE"
        with pytest.raises(KernelError) as exc2:
            q.project_overview(as_of_seq="not-a-number")
        assert exc2.value.error.code == "INVALID_INPUT"
    finally:
        store.close()


def test_timeline_pagination_token_opaque_and_cross_page_stable(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        for i in range(4):
            add_task(store, f"k{i}", f"task-{i}")

        page1 = q.project_timeline(limit=3)
        assert page1["next_page_token"]
        assert len(page1["events"]) == 3
        with pytest.raises(ValueError):
            json.loads(page1["next_page_token"])   # opaque, not JSON
        page1_as_of = page1["as_of_seq"]

        add_task(store, "k-late", "task-late")     # head advances after page 1

        page2 = q.project_timeline(limit=3, page_token=page1["next_page_token"])
        assert page2["as_of_seq"] == page1_as_of   # no jump to newer data
        keys1 = {(e["commit_seq"], e["kind"], e.get("revision_id", ""),
                  e.get("object_id", ""), e.get("event_type", "")) for e in page1["events"]}
        keys2 = {(e["commit_seq"], e["kind"], e.get("revision_id", ""),
                  e.get("object_id", ""), e.get("event_type", "")) for e in page2["events"]}
        assert not (keys1 & keys2), "pages must not overlap"

        at_as_of = q.project_timeline(limit=1000, as_of_seq=page1_as_of)
        full = {(e["commit_seq"], e["kind"], e.get("revision_id", ""), e.get("object_id", ""),
                 e.get("event_type", "")) for e in at_as_of["events"]}
        assert keys2 <= full, "continuation must stay inside the first page watermark"
        assert "task-late" not in {e.get("object_id") for e in page2["events"]}
    finally:
        store.close()


def test_page_token_tamper_cross_project_and_filter_reuse_rejected(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    other = make_store(tmp_path, project_id="proj-b")
    q = QueryService(store)
    try:
        for i in range(3):
            add_task(store, f"k{i}", f"task-{i}")
        token = q.project_timeline(limit=1)["next_page_token"]
        assert token

        body, _, sig = token.partition(".")
        tampered = f"{body[:-2]}AA.{sig}"
        with pytest.raises(KernelError) as exc:
            q.project_timeline(limit=1, page_token=tampered)
        assert exc.value.error.code == "INVALID_INPUT"

        with pytest.raises(KernelError) as exc2:
            q.project_timeline(limit=1, page_token="not-a-token")
        assert exc2.value.error.code == "INVALID_INPUT"

        # a token minted for this filter must be refused under a different filter
        with pytest.raises(KernelError) as exc3:
            q.project_timeline(object_type="task", limit=1, page_token=token)
        assert exc3.value.error.code == "INVALID_INPUT"

        # a token minted in another project store is refused here
        add_task(other, "b1", "task-b")
        other_token = QueryService(other).project_timeline(limit=1)["next_page_token"]
        if other_token:
            with pytest.raises(KernelError) as exc4:
                q.project_timeline(limit=1, page_token=other_token)
            assert exc4.value.error.code == "INVALID_INPUT"
    finally:
        other.close()
        store.close()


def test_approvals_queue_status_filter_and_invalid_status(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        assert q.approvals_queue()["queue"] == []
        append_revision(store, "ap1", "approval", "appr-1",
                        {"approval_id": "appr-1", "snapshot_id": "snap-1",
                         "snapshot_digest": "d" * 64, "status": "pending"})

        pending = q.approvals_queue(status="pending")
        assert len(pending["queue"]) == 1
        entry = pending["queue"][0]
        assert entry["approval_id"] == "appr-1"
        assert entry["snapshot_id"] == "snap-1"
        assert entry["snapshot_digest"] == "d" * 64
        assert entry["status"] == "pending"
        assert pending["pending_count"] == 1
        assert q.approvals_queue(status="approved")["queue"] == []

        with pytest.raises(KernelError) as exc:
            q.approvals_queue(status="bogus")
        assert exc.value.error.code == "INVALID_INPUT"
    finally:
        store.close()


def test_archive_status_partial_reports_archive_partial(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        assert q.archive_status()["deliveries"] == []      # legacy key
        assert q.archive_status()["partial"] is False

        store.conn.execute(
            "INSERT INTO archive_manifest (manifest_id, body_schema, body_json, digest,"
            " commit_seq, project_id) VALUES (?,?,?,?,?,?)",
            ("man-1", "archive_manifest.v1", "{}", "a" * 64, 0, PROJ))
        store.conn.execute(
            "INSERT INTO sink_receipt (manifest_id, sink, state, digest, lease, error,"
            " project_id) VALUES (?,?,?,?,?,?,?)",
            ("man-1", "exports", "succeeded", "a" * 64, None, None, PROJ))
        store.conn.execute(
            "INSERT INTO sink_receipt (manifest_id, sink, state, digest, lease, error,"
            " project_id) VALUES (?,?,?,?,?,?,?)",
            ("man-1", "cold", "failed", "a" * 64, None, "disk full", PROJ))

        with pytest.raises(KernelError) as missing:
            q.archive_status(ref("archive_manifest", "man-1"))
        assert missing.value.error.code == "REFERENCE_NOT_FOUND"
        status = q.archive_status()
        assert status["partial"] is True
        assert status["completeness"] == "incomplete"
        assert status["errors"][0]["code"] == "ARCHIVE_PARTIAL"
        assert status["main_store"]["store_id"] == "store-a"
        assert status["session_flush"]["state"] == "not_configured"
        sinks = {s["sink_id"]: s["state"] for s in status["sinks"]}
        assert sinks["exports"] == "unknown" and sinks["cold"] == "failed"
    finally:
        store.close()


def test_environment_report_no_data_vs_source_failure(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        task = add_task(store, "k1", "task-1")
        no_probe = q.environment_report(task.to_dict())
        assert no_probe["data"]["data_state"] == "no_data"
        assert no_probe["data"]["missing"] == []       # absence is not "missing"
        assert no_probe["completeness"] == "complete"

        append_revision(store, "env1", "environment_snapshot", "env-1",
                        {"task_ref": task.to_dict(), "state": "failed",
                         "probe_error": "recipe interrupted", "requirements": []})
        failed = q.environment_report(task.to_dict())
        assert failed["data"]["data_state"] == "source_failed"
        assert failed["data"]["missing"] == []         # never assume missing on failure
        assert failed["completeness"] == "incomplete"
        assert any(g.get("reason") == "environment_probe_failed" for g in failed["gaps"])
    finally:
        store.close()


def test_rebuild_is_read_only_consistent_and_detects_bad_head(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        add_task(store, "k1", "task-1")
        before = store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0]
        result = q.rebuild_read_model()
        after = store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0]
        assert before == after, "rebuild must not write"
        assert result["data"]["persisted"] is False
        assert result["data"]["requires_ddl"].startswith("projection_checkpoint")
        assert result["data"]["consistent"] is True
        assert q.rebuild_read_model(as_of_seq=result["as_of_seq"])["data"]["digest"] \
            == result["data"]["digest"]

        # a head that has no matching head_history publish is detected, not hidden
        head = store.get_head("task", "task-1", "current")
        store.conn.execute(
            "INSERT INTO entity_head (project_id, type, object_id, pointer_name, revision_id,"
            " head_version, updated_seq) VALUES (?,?,?,?,?,?,?)",
            (PROJ, "task", "task-1", "p06-stale-pointer", head["revision_id"], 1, 0))
        broken = q.rebuild_read_model()
        assert broken["data"]["consistent"] is False
        assert any(m["reason"] == "head_history_mismatch" for m in broken["data"]["mismatches"])
        store.conn.execute("DELETE FROM entity_head WHERE pointer_name='p06-stale-pointer'")
        assert q.rebuild_read_model()["data"]["consistent"] is True
    finally:
        store.close()


def test_attempts_compare_unknown_usage_not_zero_and_no_double_count(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        task = add_task(store, "k1", "task-1")
        packet = append_revision(store, "p1", "execution_packet", "packet-1",
                                 {"task_ref": task.to_dict(),
                                  "strategies": [{"strategy_id": "s1"}],
                                  "requirement_refs": [], "acceptance_refs": []})
        append_revision(store, "a1", "attempt", "attempt-1",
                        {"attempt_id": "attempt-1", "task_ref": task.to_dict(),
                         "packet_ref": packet.to_dict(), "strategy_id": "s1",
                         "status": "completed", "exit_code": 0})
        # settle revision drops the linkage: the query must still find the task
        append_revision(store, "a2", "attempt", "attempt-1",
                        {"attempt_id": "attempt-1", "status": "completed", "exit_code": 0})
        append_revision(store, "a3", "attempt", "attempt-2",
                        {"attempt_id": "attempt-2", "task_ref": task.to_dict(),
                         "packet_ref": packet.to_dict(), "strategy_id": "s1",
                         "status": "failed", "exit_code": 1})
        for name in ("attempt-manual-1", "attempt-manual-2"):
            append_revision(store, f"m-{name}", "attempt", name,
                            {"attempt_id": name, "task_ref": task.to_dict(),
                             "packet_ref": packet.to_dict(), "strategy_id": "s1",
                             "status": "completed", "source_use_key": "use-1",
                             "cost": "120"})

        report = q.attempts_compare(task.to_dict())
        data = report["data"]
        ids = {a["attempt_id"] for a in data["attempts"]}
        assert {"attempt-1", "attempt-2", "attempt-manual-1", "attempt-manual-2"} == ids
        assert data["comparability"]["comparable"] is True
        assert "attempt-2" in data["failures_retained"]

        cost = data["cost"]
        assert cost["missing_usage_is_not_zero"] is True
        assert any(u["attempt_id"] == "attempt-1" for u in cost["unknown"])
        assert cost["unknown"][0]["reason"] == "usage_not_reported"
        reported = {r["attempt_id"]: r["amount"] for r in cost["reported"]}
        assert reported == {"attempt-manual-1": "120"}
        assert {d["attempt_id"] for d in cost["deduplicated"]} == {"attempt-manual-2"}
        assert cost["total"] is None, "a known total must not hide unknown usage"
        assert cost["completeness"] == "incomplete"
    finally:
        store.close()
