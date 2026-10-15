"""Effect replay and cancellation regressions over durable project stores."""
from pathlib import Path
import pytest
from project_kernel.application.attempt.service import AttemptService
from project_kernel.contracts.dto import ObjectRef, ProviderCapabilities
from project_kernel.evidence import ArtifactStorage
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, context

class CountingExecutor:
    def __init__(self,status="completed"):
        self.calls=0
        self.status=status
    def capabilities(self):
        return ProviderCapabilities("counting",("run",),"directory_only")
    def run(self,strategy,root):
        self.calls+=1
        return {"status":self.status,"stdout":b"kept output","stderr":b"kept error","exit_code":0}

def test_replay_and_restart_do_not_restart_provider_and_keep_output(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    p=prepare_dispatch(store,tmp_path)
    exe=CountingExecutor()
    storage=ArtifactStorage(tmp_path/"artifacts")
    svc=AttemptService(store,exe,artifact_storage=storage)
    data={"packet_ref":p["packet"].to_dict(),"strategy_id":"s1","execution_root_ref":p["roots"]["s1"].to_dict()}
    ctx=context(store,"start",data)
    first=svc.attempt_start(ctx,data)
    assert svc.attempt_start(ctx,data)==first
    head=store.get_head("attempt",first.operation_id,"current")
    body=store.get_revision(ObjectRef("proj-a","attempt",first.operation_id,head["revision_id"]))["payload"]
    assert body["task_ref"]==p["task"].to_dict()
    assert body["output_artifacts"]["stdout"]["sha256"]
    assert body["output_artifacts"]["stderr"]["sha256"]
    store.close()
    store=make_store(tmp_path,project_id="proj-a")
    try:
        assert AttemptService(store,exe,artifact_storage=storage).attempt_start(ctx,data)==first
        assert exe.calls==1
    finally: store.close()

def test_unknown_cancel_without_provider_confirmation_stays_pending(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path)
        exe=CountingExecutor("unknown")
        svc=AttemptService(store,exe,artifact_storage=ArtifactStorage(tmp_path/"artifacts"))
        data={"packet_ref":p["packet"].to_dict(),"strategy_id":"s1","execution_root_ref":p["roots"]["s1"].to_dict()}
        started=svc.attempt_start(context(store,"start",data),data)
        cancelled=svc.attempt_cancel(context(store,"cancel"),{"attempt_ref":started.object_refs[0].to_dict(),"reason":"stop"})
        body=store.get_revision(cancelled.object_refs[0])["payload"]
        assert body["status"]=="unknown" and body["cancel_status"]=="pending"
        assert exe.calls==1
    finally: store.close()

@pytest.mark.parametrize("field",["strategy","root","revision"])
def test_start_requires_exact_packet_and_strategy_root(tmp_path,field):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path,strategies=("s1","s2"))
        exe=CountingExecutor()
        svc=AttemptService(store,exe,artifact_storage=ArtifactStorage(tmp_path/"artifacts"))
        data={"packet_ref":p["packet"].to_dict(),"strategy_id":"s1","execution_root_ref":p["roots"]["s1"].to_dict()}
        if field=="strategy": data["strategy_id"]="undeclared"
        if field=="root": data["execution_root_ref"]=p["roots"]["s2"].to_dict()
        if field=="revision": data["packet_ref"]["revision_id"]="rev-404"
        result=svc.attempt_start(context(store,"start",data),data)
        assert result.status=="rejected"
        assert exe.calls==0
    finally: store.close()


def test_provider_cannot_overwrite_kernel_owned_execution_identity(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path)
        class ForgedExecutor(CountingExecutor):
            def run(self,strategy,root):
                result=super().run(strategy,root)
                result.update(task_ref={"project_id":"foreign"},packet_ref={},strategy_id="other",
                    epoch="99",provider_id="foreign",execution_handle_id="other",attempt_id="fake")
                return result
        svc=AttemptService(store,ForgedExecutor(),artifact_storage=ArtifactStorage(tmp_path/"artifacts"))
        data={"packet_ref":p["packet"].to_dict(),"strategy_id":"s1","execution_root_ref":p["roots"]["s1"].to_dict()}
        receipt=svc.attempt_start(context(store,"identity"),data)
        body,_=svc._head(receipt.operation_id)
        assert body["task_ref"]==p["task"].to_dict()
        assert body["packet_ref"]==p["packet"].to_dict()
        assert body["attempt_id"]==receipt.operation_id
        assert body["strategy_id"]=="s1" and body["epoch"]=="1" and body["provider_id"]=="counting"
        assert body["execution_handle_id"]!="other"
        source=store.get_revision(ObjectRef.from_dict(body["source_result_ref"]))["payload"]
        assert source["result"]["provider_id"]=="foreign"
    finally:store.close()
