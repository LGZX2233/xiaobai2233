"""Effect ownership and durable uncertainty through real delivery services."""
import pytest
from project_kernel.application.delivery.service import DeliveryService
from project_kernel.contracts.errors import KernelError
from project_kernel.data.queries.service import QueryService
from project_kernel.data.store.store import Store
from project_kernel.data.store.uow import UnitOfWork
from p04_delivery.helpers import Harness, ctx, patch_object


def test_apply_replay_after_restart_calls_exporter_once(tmp_path,monkeypatch):
    h=Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval,digest=h.approved()
        calls=[]
        export=h.exporter.export
        def counted(*args, **kwargs):
            calls.append(args[0].manifest_id)
            return export(*args, **kwargs)
        monkeypatch.setattr(h.exporter,"export",counted)
        first=h.svc.apply_delivery(ctx("apply-once"),approval,"snap-1",digest)
        assert h.svc.apply_delivery(ctx("apply-once"),approval,"snap-1",digest)==first
        path=h.store.conn.execute("PRAGMA database_list").fetchone()[2]
        h.store.close()
        h.store=Store.open_project(__import__("pathlib").Path(path),"proj-a","store-a")
        h.svc=DeliveryService(h.store,provider=h.provider,artifact_storage=h.storage)
        assert h.svc.apply_delivery(ctx("apply-once"),approval,"snap-1",digest)==first
        assert len(calls)==1
    finally:h.close()


@pytest.mark.parametrize("change",["revoked","expired","candidate"])
def test_apply_start_rechecks_approval_and_candidate_after_claim(tmp_path,change):
    h=Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval,digest=h.approved()
        claimed=h.svc.claim_delivery(ctx("claim"),approval,digest)
        oid=claimed.object_refs[0].object_id
        if change=="revoked":
            patch_object(h.store,"approval",approval,{"status":"revoked"},"revoke")
        elif change=="expired":
            patch_object(h.store,"approval",approval,{"expires_at":"2000-01-01T00:00:00Z"},"expire")
        else:
            patch_object(h.store,"candidate_manifest",h.candidate.object_id,{"candidate_digest":"c"*64},"change")
        result=h.svc.apply_start_delivery(ctx("start"),oid)
        assert result.status=="rejected"
        assert h.operation(oid)["status"]=="claimed"
        assert not (tmp_path/"exports"/oid).exists()
    finally:h.close()


def test_effect_succeeds_but_settlement_is_lost_then_reconciled(tmp_path,monkeypatch):
    h=Harness(tmp_path)
    try:
        h.to_delivery_ready()
        approval,digest=h.approved()
        execute=UnitOfWork.execute
        def lose_settlement(self,callback):
            if self.command_kind=="delivery.settle":
                raise OSError("simulated loss after publication")
            return execute(self,callback)
        monkeypatch.setattr(UnitOfWork,"execute",lose_settlement)
        with pytest.raises(OSError):
            h.svc.apply_delivery(ctx("lost"),approval,"snap-1",digest)
        monkeypatch.setattr(UnitOfWork,"execute",execute)
        oid=Harness.operation_id_for("lost")
        assert h.operation(oid)["status"]=="applying"
        blocked = QueryService(h.store).project_overview()
        assert len(blocked["blockers"]) == 1
        blocked_seq = blocked["as_of_seq"]
        published=(tmp_path/"exports"/oid/"manifest.json").read_bytes()
        monkeypatch.setattr(h.exporter,"export",lambda *a,**k:pytest.fail("external effect must not repeat"))
        replay=h.svc.apply_delivery(ctx("lost"),approval,"snap-1",digest)
        assert replay.operation_id==oid
        h.svc.delivery_reconcile(ctx("reconcile"),oid)
        assert h.operation(oid)["status"]=="applied"
        assert QueryService(h.store).project_overview()["blockers"] == []
        historical = QueryService(h.store).project_overview(as_of_seq=blocked_seq)
        assert len(historical["blockers"]) == 1
        assert (tmp_path/"exports"/oid/"manifest.json").read_bytes()==published
    finally:h.close()


def test_verification_provider_failure_has_durable_unknown_operation(tmp_path):
    h=Harness(tmp_path)
    try:
        h.to_attempt()
        calls=[]
        def unavailable(items):
            assert not h.store.conn.in_transaction
            calls.append(1)
            raise OSError("checker unavailable")
        def run():
            return h.svc.verification_run(ctx("provider-failed"),h.attempt_ref,h.candidate,
                acceptance_refs=[h.acceptance_ref],check_provider=unavailable,evidence_mode="test")
        with pytest.raises(KernelError):run()
        replay=run()
        state=QueryService(h.store).operation_status(replay.operation_id)
        assert state["status"]=="unknown" and state["error"]["type"]=="OSError"
        assert len(calls)==1
        assert not QueryService(h.store).latest_revisions("verification")
    finally:h.close()


def test_close_keeps_archive_incomplete_when_source_has_a_gap(tmp_path):
    h=Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation,_,_=h.applied()
        UnitOfWork(h.store,ctx("source-gap"),"source.ingest").execute(lambda u:u.source.ingest(
            "host:session:1",[{"host_id":"host","origin_session_id":"session","log_generation":"1",
                "source_seq":"2","body":{"message":"not contiguous"}}]))
        closed=h.svc.task_close(ctx("close"),h.task_ref,operation)
        state=h.store.get_revision(closed.object_refs[2])["payload"]
        assert state["source_flushed"] is False
        assert state["overall"]!="complete"
    finally:h.close()


def test_approved_delivery_cannot_redirect_to_another_sink(tmp_path):
    h=Harness(tmp_path)
    try:
        h.to_delivery_ready()
        patch_object(h.store,"delivery_target","dt1",{"sink_id":"other-sink"},"target")
        # Build a fresh snapshot pinned to the other target before approving it.
        from project_kernel.contracts.dto import ObjectRef
        head=h.store.get_head("delivery_target","dt1","current")
        h.target_ref=ObjectRef("proj-a","delivery_target","dt1",head["revision_id"])
        approval,digest=h.approved()
        receipt=h.svc.apply_delivery(ctx("wrong-sink"),approval,"snap-1",digest)
        assert receipt.status=="rejected" and receipt.error.code=="PERMISSION_DENIED"
        assert not h.svc._delivery_heads()
    finally:h.close()


def test_two_connections_close_once_and_keep_one_manifest(tmp_path):
    import threading
    from pathlib import Path
    h=Harness(tmp_path)
    try:
        h.to_delivery_ready()
        operation,_,_=h.applied()
        path=Path(h.store.conn.execute("PRAGMA database_list").fetchone()[2])
        barrier=threading.Barrier(2,timeout=3)
        receipts=[]
        failures=[]
        def worker(key):
            store=None
            try:
                store=Store.open_project(path,"proj-a","store-a")
                service=DeliveryService(store,provider=h.provider,artifact_storage=h.storage)
                barrier.wait()
                receipts.append(service.task_close(ctx(key),h.task_ref,operation))
            except BaseException as exc:
                failures.append(exc)
                barrier.abort()
            finally:
                if store is not None:store.close()
        threads=[threading.Thread(target=worker,args=(key,),daemon=True) for key in ("close-a","close-b")]
        for thread in threads:thread.start()
        for thread in threads:thread.join(6)
        assert not any(thread.is_alive() for thread in threads)
        assert not failures
        assert sorted(receipt.status for receipt in receipts)==["committed","rejected"]
        assert len(QueryService(h.store).latest_revisions("archive_manifest"))==1
        assert h.task_phase()=="closed"
    finally:h.close()
