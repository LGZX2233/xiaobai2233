"""UoW replay, rejection races and known/unknown commit outcomes."""
from __future__ import annotations

import sqlite3
import threading

import pytest

from project_kernel.contracts import ObjectRef, sha256_digest
from project_kernel.contracts.errors import (
    BlockError, KernelError, SafeDetail, sqlite_busy, temporary_unavailable,
)
from project_kernel.data.store.uow import UnitOfWork

from .helpers import make_context, make_store, record_payload


def _reject(error):
    def callback(handles):
        raise KernelError(error)
    return callback


def _assert_no_commit(store, key):
    assert not store.conn.in_transaction
    assert store.get_receipt("user-1", key) is None
    assert store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0] == 0
    assert store.conn.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0] == 0
    assert store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == 0


def test_rejected_receipt_replays_every_field(tmp_path):
    store = make_store(tmp_path)
    related = ObjectRef("proj-a", "requirement", "req-1", "rev-1")
    error = BlockError("REQUIRED_FACT_UNKNOWN", "missing evidence", category="business",
                       safe_details=(SafeDetail("fact", "missing"),),
                       recovery_action="provide evidence", related_refs=(related,))
    uow = UnitOfWork(store, make_context(key="reject"), "test.command")
    try:
        first = uow.execute(_reject(error))
        assert uow.did_commit is True
        persisted = store.get_receipt("user-1", "reject")["receipt"]
        called = []
        replay = uow.execute(lambda handles: called.append(True))
        assert uow.did_commit is False
        assert called == []
        assert replay.to_dict() == first.to_dict() == persisted
        assert replay.error.safe_details == error.safe_details
        assert replay.error.related_refs == (related.to_dict(),)
    finally:
        store.close()


@pytest.mark.parametrize("error", [
    temporary_unavailable("retry when recovered"),
    sqlite_busy(),
    BlockError("EXTERNAL_OUTCOME_UNKNOWN", "not known", retryable=True,
               category="infrastructure"),
    BlockError("TEMPORARY_UNAVAILABLE", "unknown category", category="unknown"),
])
def test_transient_error_does_not_poison_original_key(tmp_path, error):
    store = make_store(tmp_path)
    uow = UnitOfWork(store, make_context(key="retry"), "test.command")
    try:
        def failing(handles):
            ref = handles.records.append_revision("requirement", "req-1",
                                                  record_payload("partial"), "requirement.v1")
            handles.records.publish_head(ref, "current")
            handles.audit("discarded.event")
            raise KernelError(error)

        with pytest.raises(KernelError) as failure:
            uow.execute(failing)
        assert failure.value.error == error
        assert uow.did_commit is False
        _assert_no_commit(store, "retry")
        assert store.get_head("requirement", "req-1", "current") is None
        called = []
        receipt = uow.execute(lambda handles: called.append(True))
        assert called == [True]
        assert receipt.status == "committed"
        assert receipt.commit_seq == "1"
        assert uow.did_commit is True
        assert store.conn.execute("SELECT event_type FROM audit_event").fetchall() == [
            ("command.committed",)]
    finally:
        store.close()


@pytest.mark.parametrize("different_hash", [False, True])
def test_rejection_reacquires_lock_and_obeys_winning_key(tmp_path, different_hash):
    store = make_store(tmp_path)
    other = make_store(tmp_path)
    winner = {}
    ctx = make_context(key="raced-key")
    winning_ctx = make_context(key="raced-key", input_hash=sha256_digest({"different": True}))         if different_hash else ctx

    class InterleavedRejection(UnitOfWork):
        def _commit_rejection(self, error, principal):
            # The callback transaction has rolled back. The other real connection
            # wins the key before this invocation reacquires the write lock.
            assert not store.conn.in_transaction
            winner["receipt"] = UnitOfWork(other, winning_ctx, "test.command").execute(
                lambda handles: None)
            return super()._commit_rejection(error, principal)

    uow = InterleavedRejection(store, ctx, "test.command")
    try:
        rejection = _reject(BlockError("REQUIRED_FACT_UNKNOWN", "missing"))
        if different_hash:
            with pytest.raises(KernelError) as failure:
                uow.execute(rejection)
            assert failure.value.error.code == "IDEMPOTENCY_CONFLICT"
        else:
            receipt = uow.execute(rejection)
            assert receipt.to_dict() == winner["receipt"].to_dict()
        assert uow.did_commit is False
        assert not store.conn.in_transaction
        assert store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0] == 1
        assert store.conn.execute("SELECT COUNT(*) FROM command_receipt").fetchone()[0] == 1
        assert store.get_receipt("user-1", "raced-key")["receipt"] == winner["receipt"].to_dict()
    finally:
        other.close()
        store.close()


def test_busy_before_begin_is_retryable_and_does_not_consume_key(tmp_path):
    store = make_store(tmp_path)
    blocker = make_store(tmp_path)
    store.conn.execute("PRAGMA busy_timeout = 1")
    uow = UnitOfWork(store, make_context(key="busy"), "test.command")
    try:
        blocker.conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(KernelError) as failure:
            uow.execute(lambda handles: None)
        assert failure.value.error.code == "SQLITE_BUSY"
        assert failure.value.error.retryable is True
        assert uow.did_commit is False
        _assert_no_commit(store, "busy")
        blocker.conn.execute("ROLLBACK")
        assert uow.execute(lambda handles: None).status == "committed"
        assert uow.did_commit is True
    finally:
        blocker.close()
        store.close()


@pytest.mark.parametrize("reject", [False, True])
def test_known_precommit_failure_is_not_unknown(tmp_path, reject):
    store = make_store(tmp_path)
    uow = UnitOfWork(store, make_context(key="precommit"), "test.command")
    try:
        store.conn.execute("CREATE TRIGGER fail_commit_body BEFORE INSERT ON commit_log "
                           "BEGIN SELECT RAISE(ABORT, 'deterministic precommit failure'); END")
        callback = _reject(BlockError("REQUIRED_FACT_UNKNOWN", "missing")) if reject             else lambda handles: None
        with pytest.raises(KernelError) as failure:
            uow.execute(callback)
        assert failure.value.error.code == "TEMPORARY_UNAVAILABLE"
        assert failure.value.error.retryable is True
        assert isinstance(failure.value.__cause__, sqlite3.IntegrityError)
        assert uow.did_commit is False
        _assert_no_commit(store, "precommit")
        store.conn.execute("DROP TRIGGER fail_commit_body")
        assert uow.execute(lambda handles: None).commit_seq == "1"
    finally:
        store.close()


class _CommitFailureConnection:
    def __init__(self, connection, *, after_commit):
        self.connection = connection
        self.after_commit = after_commit
        self.fail_once = True

    def execute(self, sql, *args):
        if sql == "COMMIT" and self.fail_once:
            self.fail_once = False
            if self.after_commit:
                self.connection.execute(sql, *args)
            raise sqlite3.OperationalError("injected commit transport failure")
        return self.connection.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.connection, name)


@pytest.mark.parametrize("after_commit", [False, True])
def test_commit_exception_distinguishes_successful_rollback_from_lost_ack(tmp_path, after_commit):
    store = make_store(tmp_path)
    original = store.conn
    store.conn = _CommitFailureConnection(original, after_commit=after_commit)
    uow = UnitOfWork(store, make_context(key="commit-failure"), "test.command")
    calls = []
    try:
        with pytest.raises(KernelError) as failure:
            uow.execute(lambda handles: calls.append(True))
        assert uow.did_commit is False
        assert not original.in_transaction
        if after_commit:
            assert failure.value.error.code == "COMMIT_OUTCOME_UNKNOWN"
            receipt = store.get_receipt("user-1", "commit-failure")["receipt"]
            replay = uow.execute(lambda handles: calls.append(True))
            assert replay.to_dict() == receipt
            assert uow.did_commit is False
            assert calls == [True]
        else:
            assert failure.value.error.code == "TEMPORARY_UNAVAILABLE"
            _assert_no_commit(store, "commit-failure")
            assert uow.execute(lambda handles: calls.append(True)).status == "committed"
            assert uow.did_commit is True
            assert calls == [True, True]
    finally:
        store.close()


def test_non_sqlite_commit_body_exception_rolls_back(tmp_path):
    store = make_store(tmp_path)
    uow = UnitOfWork(store, make_context(key="serialize"), "test.command")
    try:
        def callback(handles):
            handles.audit("invalid.refs", object_refs={object()})

        with pytest.raises(TypeError):
            uow.execute(callback)
        _assert_no_commit(store, "serialize")
        assert uow.did_commit is False
    finally:
        store.close()


def test_concurrent_same_key_commits_once_and_identifies_owner(tmp_path):
    make_store(tmp_path).close()
    barrier = threading.Barrier(2, timeout=5)
    results = []
    errors = []
    calls = []
    lock = threading.Lock()

    def worker():
        store = None
        try:
            store = make_store(tmp_path)
            uow = UnitOfWork(store, make_context(key="same-key"), "test.command")
            barrier.wait()

            def callback(handles):
                with lock:
                    calls.append(True)
                handles.outcome.operation_id = "operation-1"

            receipt = uow.execute(callback)
            with lock:
                results.append((receipt.to_dict(), uow.did_commit))
        except BaseException as error:
            barrier.abort()
            with lock:
                errors.append(error)
        finally:
            if store is not None:
                store.close()

    workers = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join(10)
    assert not any(thread.is_alive() for thread in workers)
    assert errors == []
    assert calls == [True]
    assert len(results) == 2
    assert results[0][0] == results[1][0]
    assert sorted(did_commit for _, did_commit in results) == [False, True]
    store = make_store(tmp_path)
    try:
        assert store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0] == 1
        assert store.conn.execute("SELECT COUNT(*) FROM command_receipt").fetchone()[0] == 1
    finally:
        store.close()


@pytest.mark.parametrize("different_hash", [False, True])
def test_initial_lock_recheck_obeys_winner_without_committing_rejection(tmp_path, different_hash):
    store = make_store(tmp_path)
    other = make_store(tmp_path)
    winner = {}
    ctx = make_context(key="before-lock")
    winning_ctx = make_context(key="before-lock", input_hash=sha256_digest({"changed": True})) \
        if different_hash else ctx

    class InterleavedBegin(UnitOfWork):
        def _begin(self):
            winner["receipt"] = UnitOfWork(other, winning_ctx, "test.command").execute(
                lambda handles: None)
            super()._begin()

    uow = InterleavedBegin(store, ctx, "test.command")
    called = []
    try:
        if different_hash:
            with pytest.raises(KernelError) as failure:
                uow.execute(lambda handles: called.append(True))
            assert failure.value.error.code == "IDEMPOTENCY_CONFLICT"
        else:
            receipt = uow.execute(lambda handles: called.append(True))
            assert receipt.to_dict() == winner["receipt"].to_dict()
        assert called == []
        assert uow.did_commit is False
        assert not store.conn.in_transaction
        assert store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0] == 1
    finally:
        other.close()
        store.close()


@pytest.mark.parametrize("operation_id", [None, "operation-1"])
def test_success_receipt_replay_preserves_references_and_commit_metadata(tmp_path, operation_id):
    store = make_store(tmp_path)
    uow = UnitOfWork(store, make_context(key="success"), "test.command")
    try:
        def callback(handles):
            ref = handles.records.append_revision("requirement", "req-1",
                                                  record_payload("saved"), "requirement.v1")
            handles.records.publish_head(ref, "current")
            handles.outcome.object_refs = (ref,)
            handles.outcome.result_refs = (ref,)
            handles.outcome.operation_id = operation_id
            handles.audit("first.event")
            handles.audit("second.event")

        receipt = uow.execute(callback)
        assert uow.did_commit is True
        replay = uow.execute(lambda handles: pytest.fail("replay must not call business handler"))
        assert replay.to_dict() == receipt.to_dict()
        assert replay.event_cursor.event_index == 1
        assert replay.object_refs == receipt.object_refs
        assert replay.result_refs == receipt.result_refs
        assert replay.operation_id == operation_id
        assert uow.did_commit is False
    finally:
        store.close()
