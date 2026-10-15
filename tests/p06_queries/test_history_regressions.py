"""Historical views use committed evidence and retain unknown legacy history."""
import pytest

from project_kernel.contracts.dto import ObjectRef
from project_kernel.contracts.errors import KernelError
from project_kernel.data.queries.service import QueryService
from project_kernel.data.queries.watermarks import ReadEnvelope
from project_kernel.data.store.uow import UnitOfWork
from p01_store.helpers import make_context, make_store


def publish(store, key, kind, oid, body):
    def write(h):
        head = store.get_head(kind, oid, "current")
        ref = h.records.append_revision(kind, oid, body, kind + ".v1")
        h.records.publish_head(ref, "current", str(head["head_version"]) if head else None)
        h.outcome.object_refs = (ref,)
    return UnitOfWork(store, make_context(key=key), "test.seed").execute(write)


def test_blocker_resolution_preserves_historical_open_and_rejects_stale_update(tmp_path):
    store = make_store(tmp_path)
    try:
        task = publish(store, "task", "task", "task-1", {"phase": "delivery"}).object_refs[0]
        evidence = publish(store, "effect", "delivery", "op", {"status": "unknown"}).object_refs[0]
        def opening(h):
            h.outcome.object_refs = (h.blockers.open("b1", task, "UNKNOWN_EFFECT", evidence),)
        opened = UnitOfWork(store, make_context(key="open"), "test.open").execute(opening)
        blocker = opened.object_refs[0]
        resolved = publish(store, "effect-done", "delivery", "op", {"status": "applied"}).object_refs[0]
        def resolving(h):
            h.outcome.object_refs = (h.blockers.resolve(blocker, resolved, expected_head_version="1"),)
        result = UnitOfWork(store, make_context(key="resolve"), "test.resolve").execute(resolving)
        assert result.status == "committed"
        query = QueryService(store)
        assert query.project_overview()["blockers"] == []
        old = query.project_overview(as_of_seq=opened.commit_seq)
        assert old["blockers"][0]["evidence_ref"] == evidence.to_dict()
        assert old["data"]["completeness"] == old["completeness"] == "incomplete"
        assert "blocker_history_unavailable" not in old["required_missing"]
        repeated = UnitOfWork(store, make_context(key="stale-resolve"), "test.resolve").execute(resolving)
        assert repeated.status == "rejected" and repeated.error.code == "STALE_REVISION"
        assert len(query.list_revisions("blocker")) == 2
    finally:
        store.close()


def test_blocker_rejects_foreign_evidence_without_partial_state(tmp_path):
    store = make_store(tmp_path)
    try:
        task = publish(store, "task", "task", "task-1", {}).object_refs[0]
        receipt = UnitOfWork(store, make_context(key="foreign"), "test.open").execute(
            lambda h: h.blockers.open("b", task, "UNKNOWN",
                                      ObjectRef("other", "delivery", "op", "rev-1")))
        assert receipt.status == "rejected" and receipt.error.code == "SCOPE_MISMATCH"
        assert not store.conn.execute("SELECT 1 FROM blocker").fetchone()
    finally:
        store.close()


def test_legacy_blockers_remain_unknown_at_historical_watermark(tmp_path):
    store = make_store(tmp_path)
    try:
        first = publish(store, "first", "task", "t", {})
        publish(store, "second", "task", "t", {"phase": "design"})
        store.conn.execute("INSERT INTO blocker VALUES(?,?,?,?,?,?)",
                           ("legacy", "t", "OLD", None, "resolved-later", "proj-a"))
        report = QueryService(store).project_overview(as_of_seq=first.commit_seq)
        assert "blocker_history_unavailable" in report["required_missing"]
        assert report["data"]["completeness"] == report["completeness"] == "incomplete"
    finally:
        store.close()


def test_huge_source_gap_is_bounded_for_current_and_historical_views(tmp_path):
    store = make_store(tmp_path)
    try:
        high = 10 ** 35
        event = {"host_id": "host", "origin_session_id": "session", "log_generation": "1",
                 "source_seq": str(high), "body": {}}
        ingested = UnitOfWork(store, make_context(key="ingest"), "source.ingest").execute(
            lambda h: h.source.ingest("host:session:1", [event]))
        publish(store, "later", "task", "t", {})
        for watermark in (None, int(ingested.commit_seq)):
            result = ReadEnvelope(store.conn, "proj-a", "store-a").source_watermarks(
                watermark, missing_limit=3)
            stream = result["streams"][0]
            assert stream["missing"] == [1, 2, 3]
            assert stream["missing_count"] == str(high - 1) and stream["truncated"]
            assert stream["ranges"] == [{"first": "1", "last": str(high - 1)}]
            assert result["data_state"] == "gapped"
        no_sample = ReadEnvelope(store.conn, "proj-a", "store-a").source_watermarks(missing_limit=0)
        assert no_sample["data_state"] == "gapped"
        assert no_sample["streams"][0]["missing"] == []
    finally:
        store.close()


def test_archive_history_does_not_show_future_sink_receipt(tmp_path):
    store = make_store(tmp_path)
    try:
        manifest = publish(store, "manifest", "archive_manifest", "archive-1", {"required_sinks": ["exports"]})
        mref = manifest.object_refs[0].to_dict()
        first = publish(store, "pending", "archive_status", "t",
                        {"manifest_ref": mref, "required_sinks": ["exports"], "sink_states": {}})
        publish(store, "done", "archive_status", "t",
                {"manifest_ref": mref, "required_sinks": ["exports"], "sink_states": {"exports": "succeeded"},
                 "receipts": {"exports": {"digest": store.get_revision(manifest.object_refs[0])["digest"], "verified": True}}})
        store.conn.execute("INSERT INTO sink_receipt VALUES(?,?,?,?,?,?,?)",
                           ("archive-1", "exports", "succeeded", "a"*64, None, None, "proj-a"))
        query = QueryService(store)
        before = query.archive_status(mref, as_of_seq=first.commit_seq)
        assert before["sinks"][0]["state"] == "pending" and before["partial"]
        assert query.archive_status(mref)["sinks"][0]["state"] == "succeeded"
        with pytest.raises(KernelError):
            query.archive_status({**mref, "project_id": "other"})
    finally:
        store.close()


def test_legacy_sink_history_reports_unavailable(tmp_path):
    store = make_store(tmp_path)
    try:
        first = publish(store, "first", "task", "t", {})
        publish(store, "later", "task", "t", {"phase": "design"})
        store.conn.execute("INSERT INTO sink_receipt VALUES(?,?,?,?,?,?,?)",
                           ("old", "exports", "succeeded", "a"*64, None, None, "proj-a"))
        report = QueryService(store).archive_status(as_of_seq=first.commit_seq)
        assert report["sinks"] == [] and report["partial"]
        assert "sink_history_unavailable" in report["required_missing"]
    finally:
        store.close()


def test_archive_sink_uses_latest_commit_across_operation_ids(tmp_path):
    store = make_store(tmp_path)
    try:
        manifest = publish(store, "manifest", "archive_manifest", "archive-1", {})
        mref = manifest.object_refs[0].to_dict()
        for key, oid, state in (("first", "z-first", "failed"),
                                ("second", "a-second", "succeeded")):
            publish(store, key, "evidence_operation", oid,
                    {"command": "archive.export", "payload": {"manifest_ref": mref},
                     "sink_receipt": {"sink_id": "exports", "state": state,
                                      "digest": store.get_revision(manifest.object_refs[0])["digest"], "verified": True}})
        result = QueryService(store).archive_status(mref)
        assert len(result["sinks"]) == 1
        assert result["sinks"][0]["state"] == "succeeded"
        assert result["partial"] is False
    finally:
        store.close()


def test_archive_query_honors_exact_manifest_revision(tmp_path):
    store = make_store(tmp_path)
    try:
        first = publish(store, "old", "archive_manifest", "m", {"required_sinks": ["old"]})
        first_ref = first.object_refs[0].to_dict()
        publish(store, "old-status", "archive_status", "old-task",
            {"manifest_ref": first_ref, "required_sinks": ["old"], "sink_states": {"old": "failed"}})
        latest = publish(store, "new", "archive_manifest", "m", {"required_sinks": ["new"]})
        publish(store, "new-status", "archive_status", "new-task",
            {"manifest_ref": latest.object_refs[0].to_dict(), "required_sinks": ["new"], "sink_states": {"new": "succeeded"}})
        query = QueryService(store)
        requested = query.archive_status(first_ref)
        assert requested["manifests"][0]["manifest_ref"] == first_ref
        assert [s["sink_id"] for s in requested["sinks"]] == ["old"]
        assert requested["partial"]
        with pytest.raises(KernelError) as missing:
            query.archive_status({**first_ref, "revision_id": "never-existed"})
        assert missing.value.error.code == "REFERENCE_NOT_FOUND"
        with pytest.raises(KernelError):
            query.archive_status(latest.object_refs[0].to_dict(), as_of_seq=first.commit_seq)
    finally:
        store.close()


def test_required_archive_sink_is_pending_without_any_status_record(tmp_path):
    store = make_store(tmp_path)
    try:
        manifest = publish(store, "m", "archive_manifest", "m", {"required_sinks": ["exports"]})
        report = QueryService(store).archive_status(manifest.object_refs[0].to_dict())
        assert report["partial"] and report["sinks"][0]["state"] == "pending"
    finally:
        store.close()


def test_exact_old_manifest_ignores_new_delivery_and_legacy_sink_success(tmp_path):
    store = make_store(tmp_path)
    try:
        old = publish(store, "old", "archive_manifest", "m", {"required_sinks": ["exports"], "version": 1})
        new = publish(store, "new", "archive_manifest", "m", {"required_sinks": ["exports"], "version": 2})
        digest = store.get_revision(new.object_refs[0])["digest"]
        publish(store, "delivery", "delivery", "m", {"status": "applied",
            "sink_receipt": {"manifest_id": "m", "sink_id": "exports", "state": "succeeded",
                             "digest": digest, "verified": True}})
        store.conn.execute("INSERT INTO sink_receipt VALUES(?,?,?,?,?,?,?)",
            ("m", "exports", "succeeded", digest, None, None, "proj-a"))
        result = QueryService(store).archive_status(old.object_refs[0].to_dict())
        assert result["deliveries"] == []
        assert result["partial"]
        assert result["sinks"][0]["state"] == "pending"
    finally:
        store.close()
