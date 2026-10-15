"""Attempt start/settle/cancel with a real subprocess fixture + unknown semantics."""
from __future__ import annotations

import sys
import threading

import pytest

from project_kernel.application.attempt.service import AttemptService
from project_kernel.application.design.service import DesignService
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import CommandContext, ResolvedScope

from p01_store.helpers import make_store
from .fixture_executor import FixtureSubprocessExecutor

PROJ = "proj-a"


def _scope():
    return ResolvedScope(project_id=PROJ, store_id="store-a", principal_id="user-1",
                         capabilities=frozenset({"design.write", "dispatch.confirm",
                                                 "attempt.execute"}), mode="test")


def _ctx(key):
    return CommandContext(scope=_scope(), command_id="cmd", idempotency_key=key,
                          input_hash=sha256_digest({"key": key}))


def _dispatch(store):
    return _dispatch_with_task(store)[0]


def _dispatch_with_task(store):
    from pathlib import Path
    from p02_design.helpers import prepare_dispatch
    root=Path(store.conn.execute("PRAGMA database_list").fetchone()[2]).parent
    prepared=prepare_dispatch(store,root,strategies=("s1","s2","s3","s4"))
    return prepared["packet"],prepared["task"]


def _root(store, strategy="s1"):
    from project_kernel.contracts import ObjectRef
    head=store.get_head("execution_root","root-"+strategy,"current")
    return ObjectRef(PROJ,"execution_root","root-"+strategy,head["revision_id"]).to_dict()


def _service(store, executor=None):
    from pathlib import Path
    from project_kernel.evidence import ArtifactStorage
    root=Path(store.conn.execute("PRAGMA database_list").fetchone()[2]).parent
    return AttemptService(store,executor=executor,artifact_storage=ArtifactStorage(root/"artifacts"))

def test_real_subprocess_success_settles_completed(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    packet = _dispatch(store)
    # real echo command succeeds
    exe = FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('ok')"]})
    svc = _service(store, executor=exe)
    try:
        r = svc.attempt_start(_ctx("a1"), {"packet_ref": packet.to_dict(),
                                           "strategy_id": "s1",
                                           "execution_root_ref": _root(store)})
        assert r.status == "accepted"
        assert svc._attempt_status(r.operation_id) == "completed"
    finally:
        store.close()


def test_settled_attempt_keeps_task_packet_and_strategy_linkage(tmp_path):
    """A later revision must not drop the attempt's provenance (P06/P04 read the
    latest revision per object, so a settle that lost task_ref would break the
    attempt -> task / repair-chain edges)."""
    store = make_store(tmp_path, project_id=PROJ)
    packet, task_ref = _dispatch_with_task(store)
    exe = FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('ok')"]})
    svc = _service(store, executor=exe)
    try:
        r = svc.attempt_start(_ctx("a1"), {"packet_ref": packet.to_dict(),
                                           "strategy_id": "s1",
                                           "execution_root_ref": _root(store)})
        assert svc._attempt_status(r.operation_id) == "completed"
        head = store.get_head("attempt", r.operation_id, "current")
        from project_kernel.contracts import ObjectRef

        body = store.get_revision(ObjectRef(PROJ, "attempt", r.operation_id,
                                            head["revision_id"]))["payload"]
        assert body["status"] == "completed"
        assert body["task_ref"] == task_ref.to_dict()
        assert body["packet_ref"] == packet.to_dict()
        assert body["strategy_id"] == "s1"
    finally:
        store.close()


def test_real_subprocess_failure_settles_failed(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    packet = _dispatch(store)
    exe = FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "raise SystemExit(3)"]})
    svc = _service(store, executor=exe)
    try:
        r = svc.attempt_start(_ctx("a1"), {"packet_ref": packet.to_dict(),
                                           "strategy_id": "s1",
                                           "execution_root_ref": _root(store)})
        assert svc._attempt_status(r.operation_id) == "failed"
    finally:
        store.close()


def test_timeout_is_unknown_not_failed(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    packet = _dispatch(store)
    exe = FixtureSubprocessExecutor(
        {"s1": [sys.executable, "-c", "import time; time.sleep(10)"]}, timeout=0.5)
    svc = _service(store, executor=exe)
    try:
        r = svc.attempt_start(_ctx("a1"), {"packet_ref": packet.to_dict(),
                                           "strategy_id": "s1",
                                           "execution_root_ref": _root(store)})
        assert svc._attempt_status(r.operation_id) == "unknown"
    finally:
        store.close()


def test_no_provider_is_capability_unavailable(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    packet = _dispatch(store)
    svc = _service(store, executor=None)
    try:
        r = svc.attempt_start(_ctx("a1"), {"packet_ref": packet.to_dict(),
                                           "strategy_id": "s1",
                                           "execution_root_ref": _root(store)})
        assert r.status == "rejected"
        assert r.error.code == "CAPABILITY_UNAVAILABLE"
    finally:
        store.close()


def test_cross_project_packet_is_rejected(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    packet = _dispatch(store)
    exe = FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "pass"]})
    svc = _service(store, executor=exe)
    try:
        foreign = {**packet.to_dict(), "project_id": "proj-b"}
        r = svc.attempt_start(_ctx("a1"), {"packet_ref": foreign,
                                           "strategy_id": "s1",
                                           "execution_root_ref": _root(store)})
        assert r.status == "rejected"
        assert r.error.code == "SCOPE_MISMATCH"
    finally:
        store.close()


def test_concurrent_attempts_use_real_wal_and_settle_independently(tmp_path):
    """Real threads and a real provider: separate connections may run providers
    concurrently (so no write lock is held during execution) and every writer
    gets its own commit_seq."""
    store = make_store(tmp_path, project_id=PROJ)
    packet = _dispatch(store)
    store.close()

    workers = 4
    provider_barrier = threading.Barrier(workers)
    exe = FixtureSubprocessExecutor(
        {s: [sys.executable, "-c", "print('concurrent-ok')"] for s in ("s1","s2","s3","s4")},
        start_barrier=provider_barrier,
    )

    results: dict[int, tuple] = {}
    errors: list[str] = []
    lock = threading.Lock()

    def run_attempt(index):
        # Explicit threads (not a lazily sized pool) so all workers really reach
        # the shared provider barrier; a failure aborts it instead of hanging.
        try:
            worker_store = make_store(tmp_path, project_id=PROJ)
            try:
                service = _service(worker_store, executor=exe)
                receipt = service.attempt_start(
                    _ctx(f"concurrent-{index}"),
                    {"packet_ref": packet.to_dict(), "strategy_id": f"s{index+1}",
                     "execution_root_ref": _root(worker_store,f"s{index+1}")},
                )
                outcome = (receipt, service._attempt_status(receipt.operation_id))
            finally:
                worker_store.close()
        except BaseException as exc:  # noqa: BLE001 - reported through the assertions
            with lock:
                errors.append(f"{index}: {type(exc).__name__}: {exc}")
            provider_barrier.abort()
            return
        with lock:
            results[index] = outcome

    threads = [threading.Thread(target=run_attempt, args=(index,), name=f"attempt-{index}")
               for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    assert not [t.name for t in threads if t.is_alive()], "concurrent attempts did not finish"
    assert errors == [], f"concurrent attempts failed: {errors}"
    assert sorted(results) == list(range(workers))
    assert all(receipt.status == "accepted" for receipt, _ in results.values())
    assert [status for _, status in results.values()] == ["completed"] * workers
    assert len({receipt.operation_id for receipt, _ in results.values()}) == workers

    final_store = make_store(tmp_path, project_id=PROJ)
    try:
        assert final_store.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        seqs = [int(row[0]) for row in
                final_store.conn.execute("SELECT commit_seq FROM commit_log ORDER BY commit_seq")]
        # one writer, monotonically increasing sequence: no duplicate or skipped commit_seq
        assert len(seqs) == len(set(seqs))
        assert seqs == list(range(1, len(seqs) + 1))
        assert all(
            final_store.get_head("attempt", receipt.operation_id, "current") is not None
            for receipt, _ in results.values()
        )
    finally:
        final_store.close()
