"""Source ingest: contiguous cursor, gap, conflict, duplicate."""
from __future__ import annotations

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.data.store.source import SourceIngest, bounded_missing_sequences
from project_kernel.data.store.uow import UnitOfWork
from project_kernel.data.queries.watermarks import ReadEnvelope

from .helpers import make_context, make_store


def _event(seq, body):
    return {"host_id": "h1", "origin_session_id": "s1", "log_generation": "g1",
            "source_seq": str(seq), "body": body, "schema_version": "1.0.0"}


def _ingest(store, ctx, seqs):
    uow = UnitOfWork(store, ctx, "source.ingest")
    result = {}

    def cb(h):
        result["r"] = h.source.ingest(
            SourceIngest.canonical_stream_key("h1", "s1", "g1"),
            [_event(s, {"v": s}) for s in seqs])

    uow.execute(cb)
    return result["r"]


def test_contiguous_cursor_does_not_cross_gap(tmp_path):
    store = make_store(tmp_path)
    try:
        _ingest(store, make_context(key="src-1"), [1, 2, 3])
        assert store.conn.execute(
            "SELECT contiguous_seq FROM source_cursor WHERE source_stream_key=?",
            (SourceIngest.canonical_stream_key("h1", "s1", "g1"),)
        ).fetchone()[0] == "3"
        # gap: seq 5 without seq 4
        r = _ingest(store, make_context(key="src-2"), [5])
        assert r["contiguous_seq"] == "3"
        row = store.conn.execute(
            "SELECT contiguous_seq, seen_high_water, gaps_json, status FROM source_cursor"
            " WHERE source_stream_key=?",
            (SourceIngest.canonical_stream_key("h1", "s1", "g1"),)).fetchone()
        assert row[0] == "3"
        assert row[1] == "5"
        assert row[3] == "gapped"
        # fill the gap
        r2 = _ingest(store, make_context(key="src-3"), [4])
        assert r2["contiguous_seq"] == "5"
    finally:
        store.close()


def test_duplicate_same_key_same_hash(tmp_path):
    store = make_store(tmp_path)
    try:
        r1 = _ingest(store, make_context(key="src-4"), [1])
        r2 = _ingest(store, make_context(key="src-5"), [1])
        assert r2["duplicates"] == ["1"]
        assert r2["accepted"] == []
        count = store.conn.execute(
            "SELECT COUNT(*) FROM source_event WHERE host_id='h1'").fetchone()[0]
        assert count == 1
    finally:
        store.close()


def test_conflict_same_key_different_hash(tmp_path):
    store = make_store(tmp_path)
    try:
        _ingest(store, make_context(key="src-6"), [1])
        uow = UnitOfWork(store, make_context(key="src-7"), "source.ingest")

        def cb(h):
            h.source.ingest(SourceIngest.canonical_stream_key("h1", "s1", "g1"),
                            [_event(1, {"different": True})])

        receipt = uow.execute(cb)
        assert receipt.status == "rejected"
        assert receipt.error.code == "SOURCE_CONFLICT"
        # original event retained
        count = store.conn.execute(
            "SELECT COUNT(*) FROM source_event WHERE host_id='h1'").fetchone()[0]
        assert count == 1
    finally:
        store.close()


def test_delimiter_collision_streams_keep_independent_cursors_and_gaps(tmp_path):
    store = make_store(tmp_path)
    try:
        stream_a = ("a:b", "c", "1")
        stream_b = ("a", "b:c", "1")

        def ingest(key, stream, seq):
            host, session, generation = stream
            event = {"host_id": host, "origin_session_id": session,
                     "log_generation": generation, "source_seq": str(seq),
                     "body": {"seq": seq}}
            UnitOfWork(store, make_context(key=key), "source.ingest").execute(
                lambda handles: handles.source.ingest(
                    SourceIngest.canonical_stream_key(*stream), [event]))

        ingest("tuple-a-1", stream_a, 1)
        ingest("tuple-b-2", stream_b, 2)

        keys = {SourceIngest.canonical_stream_key(*stream_a),
                SourceIngest.canonical_stream_key(*stream_b)}
        assert len(keys) == 2
        cursors = {row[0]: row[1:] for row in store.conn.execute(
            "SELECT source_stream_key,contiguous_seq,seen_high_water,status FROM source_cursor")}
        assert cursors[SourceIngest.canonical_stream_key(*stream_a)] == ("1", "1", "active")
        assert cursors[SourceIngest.canonical_stream_key(*stream_b)] == ("0", "2", "gapped")

        watermarks = ReadEnvelope(store.conn, store.project_id, store.store_id).source_watermarks()
        assert watermarks["data_state"] == "gapped"
        by_key = {row["source_stream_key"]: row for row in watermarks["streams"]}
        assert by_key[SourceIngest.canonical_stream_key(*stream_a)]["contiguous_seq"] == "1"
        assert by_key[SourceIngest.canonical_stream_key(*stream_b)]["contiguous_seq"] == "0"
        assert by_key[SourceIngest.canonical_stream_key(*stream_b)]["missing"] == [1]
    finally:
        store.close()


def test_empty_source_batch_is_rejected_explicitly(tmp_path):
    store = make_store(tmp_path)
    try:
        with pytest.raises(ValueError, match="at least one event"):
            SourceIngest(store.conn, 1).ingest("unused", [])
    finally:
        store.close()


def test_missing_sequence_summary_is_bounded_for_large_gaps():
    summary = bounded_missing_sequences([1, 10**12])
    assert summary["missing"] == list(range(2, 102))
    assert summary["missing_count"] == str(10**12 - 2)
    assert summary["ranges"] == [{"first": "2", "last": str(10**12 - 1)}]
    assert summary["next_missing_seq"] == "2"
    assert summary["truncated"] is True
