"""UoW, revision/head/history, CAS and idempotency against a real SQLite file."""
from __future__ import annotations

import pytest

from project_kernel.contracts import ObjectRef, sha256_digest
from project_kernel.contracts.errors import BlockError, KernelError
from project_kernel.data.store.store import Store
from project_kernel.data.store.uow import UnitOfWork

from .helpers import make_context, make_store, record_payload


def _append_and_publish(store, ctx, object_id, payload, pointer="current"):
    uow = UnitOfWork(store, ctx, "test.command")
    ref = {}

    def cb(h):
        r = h.records.append_revision("requirement", object_id, payload, "requirement.v1")
        h.records.publish_head(r, pointer)
        ref["r"] = r
        h.outcome.object_refs = (r,)

    uow.execute(cb)
    return ref["r"]


def test_append_revision_and_publish_head(tmp_path):
    store = make_store(tmp_path)
    try:
        ctx = make_context()
        ref = _append_and_publish(store, ctx, "req-1", record_payload("t1"))
        head = store.get_head("requirement", "req-1", "current")
        assert head is not None
        assert head["revision_id"] == ref.revision_id
        assert head["head_version"] == 1
    finally:
        store.close()


def test_draft_revision_does_not_become_current(tmp_path):
    store = make_store(tmp_path)
    try:
        ctx = make_context()
        uow = UnitOfWork(store, ctx, "test.command")
        ref = {}

        def cb(h):
            ref["r"] = h.records.append_revision("requirement", "req-1",
                                                 record_payload("draft"), "requirement.v1")
            h.outcome.object_refs = (ref["r"],)

        uow.execute(cb)
        assert store.get_head("requirement", "req-1", "current") is None
        # draft pointer must be explicitly requested; nothing was auto-published
        assert store.head_as_of("requirement", "req-1", "current", 9999) is None
    finally:
        store.close()


def test_history_as_of_restores_true_published_time(tmp_path):
    store = make_store(tmp_path)
    try:
        c1 = make_context(key="k1")
        r1 = _append_and_publish(store, c1, "req-1", record_payload("v1"))
        seq1 = int(store.get_head("requirement", "req-1", "current")["updated_seq"])

        # second publish must provide the expected head version (CAS)
        c2 = make_context(key="k2")
        uow = UnitOfWork(store, c2, "test.command")
        ref2 = {}

        def cb(h):
            r2 = h.records.append_revision("requirement", "req-1", record_payload("v2"),
                                           "requirement.v1", parent_ref=r1)
            h.records.publish_head(r2, "current", expected_head_version="1")
            ref2["r"] = r2

        uow.execute(cb)
        seq2 = int(store.get_head("requirement", "req-1", "current")["updated_seq"])
        assert seq2 > seq1

        # as_of between the two publishes must still resolve to v1
        assert store.head_as_of("requirement", "req-1", "current", seq1) == r1.revision_id
        assert store.head_as_of("requirement", "req-1", "current", seq2) == ref2["r"].revision_id
    finally:
        store.close()


def test_one_commit_seq_per_transaction(tmp_path):
    store = make_store(tmp_path)
    try:
        ctx = make_context(key="k1")
        uow = UnitOfWork(store, ctx, "test.command")
        seqs = set()

        def cb(h):
            r1 = h.records.append_revision("requirement", "a", record_payload("a"), "requirement.v1")
            r2 = h.records.append_revision("requirement", "b", record_payload("b"), "requirement.v1")
            h.records.publish_head(r1, "current")
            h.records.publish_head(r2, "current")
            seqs.add(r1.revision_id)
            h.outcome.object_refs = (r1, r2)

        receipt = uow.execute(cb)
        rows = store.conn.execute(
            "SELECT DISTINCT commit_seq FROM revision WHERE command_id=?",
            (receipt.command_id,)).fetchall()
        assert len(rows) == 1
    finally:
        store.close()


def test_idempotency_same_key_same_input_returns_original(tmp_path):
    store = make_store(tmp_path)
    try:
        ctx = make_context(key="dup-1")
        _append_and_publish(store, ctx, "req-1", record_payload("t"))
        original_receipt = store.get_receipt("user-1", "dup-1")
        # identical key + identical input hash => original receipt, callback not invoked
        ctx2 = make_context(key="dup-1")
        uow = UnitOfWork(store, ctx2, "test.command")
        called = []

        receipt = uow.execute(lambda h: called.append(1))
        assert called == []
        assert receipt.command_id == original_receipt["receipt"]["command_id"]
        assert receipt.status == "committed"
        # head_version unchanged (no second publish)
        assert store.get_head("requirement", "req-1", "current")["head_version"] == 1
    finally:
        store.close()


def test_idempotency_same_key_different_input_rejected(tmp_path):
    store = make_store(tmp_path)
    try:
        _append_and_publish(store, make_context(key="dup-2"), "req-1", record_payload("t"))
        ctx = make_context(key="dup-2", input_hash=sha256_digest({"key": "other"}))
        with pytest.raises(KernelError) as exc:
            UnitOfWork(store, ctx, "test.command").execute(lambda h: None)
        assert exc.value.error.code == "IDEMPOTENCY_CONFLICT"
    finally:
        store.close()


def test_business_rejection_commits_stable_receipt_no_partial_entity(tmp_path):
    store = make_store(tmp_path)
    try:
        ctx = make_context(key="rej-1")
        uow = UnitOfWork(store, ctx, "test.command")

        def cb(h):
            h.records.append_revision("requirement", "req-x", record_payload("partial"),
                                      "requirement.v1")
            raise KernelError(BlockError(code="REQUIRED_FACT_UNKNOWN", message="missing fact",
                                         category="business"))

        receipt = uow.execute(cb)
        assert receipt.status == "rejected"
        assert receipt.error is not None
        assert receipt.error.code == "REQUIRED_FACT_UNKNOWN"
        # no partial entity persisted
        assert store.get_revision(ObjectRef("proj-a", "requirement", "req-x", "rev-1")) is None
        # stable rejection is replayed identically
        dup = UnitOfWork(store, make_context(key="rej-1"), "test.command").execute(lambda h: None)
        assert dup.status == "rejected"
    finally:
        store.close()


def test_exception_rolls_back_all_writes(tmp_path):
    store = make_store(tmp_path)
    try:
        ctx = make_context(key="boom-1")
        uow = UnitOfWork(store, ctx, "test.command")

        def cb(h):
            h.records.append_revision("requirement", "req-b", record_payload("x"), "requirement.v1")
            raise RuntimeError("disk exploded")

        with pytest.raises(RuntimeError):
            uow.execute(cb)
        assert store.get_revision(ObjectRef("proj-a", "requirement", "req-b", "rev-1")) is None
        assert store.get_receipt("user-1", "boom-1") is None
    finally:
        store.close()


def test_cas_stale_revision(tmp_path):
    store = make_store(tmp_path)
    try:
        ref = _append_and_publish(store, make_context(key="cas-1"), "req-1", record_payload("v1"))
        # stale expected version yields a durable rejected receipt (business rejection)
        uow = UnitOfWork(store, make_context(key="cas-2"), "test.command")

        def cb(h):
            r2 = h.records.append_revision("requirement", "req-1", record_payload("v2"),
                                           "requirement.v1", parent_ref=ref)
            h.records.publish_head(r2, "current", expected_head_version="0")  # wrong

        receipt = uow.execute(cb)
        assert receipt.status == "rejected"
        assert receipt.error.code == "STALE_REVISION"
        assert store.get_head("requirement", "req-1", "current")["head_version"] == 1
    finally:
        store.close()


def test_read_only_store_rejects_write(tmp_path):
    store = make_store(tmp_path)
    try:
        _append_and_publish(store, make_context(key="ro-1"), "req-1", record_payload("t"))
    finally:
        store.close()
    ro = make_store(tmp_path, project_id="proj-a", store_id="store-a", read_only=True)
    try:
        ctx = make_context(key="ro-2")
        with pytest.raises(KernelError) as exc:
            UnitOfWork(ro, ctx, "test.command").execute(lambda h: None)
        assert exc.value.error.code == "PERMISSION_DENIED"
        assert ro.get_head("requirement", "req-1", "current") is not None
    finally:
        ro.close()


def test_two_projects_are_isolated(tmp_path):
    a = make_store(tmp_path, project_id="proj-a", store_id="store-a")
    b = make_store(tmp_path, project_id="proj-b", store_id="store-b")
    try:
        ctx_a = make_context()
        _append_and_publish(a, ctx_a, "req-1", record_payload("a"))
        assert a.get_head("requirement", "req-1", "current") is not None
        # project B has no such object, and cannot read project A's data
        assert b.get_head("requirement", "req-1", "current") is None
        assert b.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == 0
    finally:
        a.close()
        b.close()


def test_cross_project_reference_is_not_found(tmp_path):
    store = make_store(tmp_path, project_id="proj-a")
    try:
        ref = _append_and_publish(store, make_context(), "req-1", record_payload("a"))
        # a foreign project_id on the same store is rejected at read time
        foreign = ObjectRef("proj-b", ref.object_type, ref.object_id, ref.revision_id)
        assert store.get_revision(foreign) is None
        with pytest.raises(KernelError) as exc:
            from project_kernel.data.store.records import Records
            Records(store.conn, "proj-b", 1, "c", "u").read(
                "requirement", "req-1", as_of_seq=9999, pointer_name="current")
        assert exc.value.error.code == "REFERENCE_NOT_FOUND"
    finally:
        store.close()


@pytest.mark.parametrize("read_only", [False, True])
@pytest.mark.parametrize("project_id,store_id", [("other", "store-a"), ("proj-a", "other")])
def test_project_file_cannot_be_reopened_under_another_identity(tmp_path, read_only, project_id, store_id):
    store = make_store(tmp_path)
    store.close()
    with pytest.raises(KernelError) as exc:
        Store.open_project(tmp_path / "proj-a.sqlite", project_id, store_id, read_only=read_only)
    assert exc.value.error.code == "SCOPE_MISMATCH"
    valid = make_store(tmp_path)
    try:
        assert valid.get_project_meta()["store_id"] == "store-a"
    finally:
        valid.close()


@pytest.mark.parametrize("read_only", [False, True])
def test_failed_migration_closes_connection_and_releases_writer_lease(tmp_path, monkeypatch, read_only):
    import sqlite3
    from project_kernel.data.store import migrations

    store = make_store(tmp_path)
    store.close()
    captured = []
    method = "verify_migrations" if read_only else "apply_migrations"
    original = getattr(migrations, method)

    def fail(connection, required):
        captured.append(connection)
        raise RuntimeError("injected initialization failure")

    monkeypatch.setattr(migrations, method, fail)
    with pytest.raises(RuntimeError, match="injected"):
        make_store(tmp_path, read_only=read_only)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0].execute("SELECT 1")
    monkeypatch.setattr(migrations, method, original)
    reopened = make_store(tmp_path)
    reopened.close()


@pytest.mark.parametrize("read_only", [False, True])
def test_unsupported_persisted_schema_stamp_is_rejected(tmp_path, read_only):
    store = make_store(tmp_path)
    store.conn.execute("UPDATE project_meta SET schema_version='999.0.0'")
    store.close()
    with pytest.raises(KernelError) as exc:
        make_store(tmp_path, read_only=read_only)
    assert exc.value.error.code == "SCHEMA_INCOMPATIBLE"
