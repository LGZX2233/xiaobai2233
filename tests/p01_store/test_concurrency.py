"""Concurrent writers: the commit sequence is allocated under the write lock.

Regression for a real defect found by P03/P13 concurrency stress: `next_commit_seq`
used to be read *before* `BEGIN IMMEDIATE`, so two writers could pick the same
sequence and the second one failed with a false COMMIT_OUTCOME_UNKNOWN.
"""
from __future__ import annotations

import threading

from project_kernel.data.store.uow import UnitOfWork

from .helpers import make_context, make_store, record_payload


def _write_on_a_fresh_connection(tmp_path, key, results, errors, lock):
    store = make_store(tmp_path)
    try:
        ctx = make_context(key=key)
        ref = {}

        def cb(h):
            r = h.records.append_revision("requirement", f"req-{key}", record_payload(key),
                                          "requirement.v1")
            h.records.publish_head(r, "current")
            h.outcome.object_refs = (r,)
            ref["r"] = r

        receipt = UnitOfWork(store, ctx, "test.command").execute(cb)
        with lock:
            results[key] = (receipt.commit_seq, ref["r"].revision_id)
    except BaseException as exc:  # noqa: BLE001 - surfaced through the assertions
        with lock:
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
    finally:
        store.close()


def test_concurrent_writers_never_collide_on_commit_seq(tmp_path):
    make_store(tmp_path).close()  # migrate once, then contend with real threads

    workers = 4
    results: dict[str, tuple[str, str]] = {}
    errors: list[str] = []
    lock = threading.Lock()
    threads = [threading.Thread(target=_write_on_a_fresh_connection,
                                args=(tmp_path, f"k{index}", results, errors, lock))
               for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    assert not [t.name for t in threads if t.is_alive()], "concurrent writers did not finish"
    assert errors == []
    assert len(results) == workers
    seqs = sorted(int(commit_seq) for commit_seq, _ in results.values())
    assert seqs == list(range(1, workers + 1))

    store = make_store(tmp_path)
    try:
        rows = [int(row[0]) for row in
                store.conn.execute("SELECT commit_seq FROM commit_log ORDER BY commit_seq")]
        assert rows == list(range(1, workers + 1))
        assert all(store.get_head("requirement", f"req-k{index}", "current") is not None
                   for index in range(workers))
    finally:
        store.close()
