"""Real baselines, exact references, immutable confirmation and CAS."""
from copy import deepcopy
import pytest
from project_kernel.application.design.service import DesignService
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import ExpectedHead
from p01_store.helpers import make_store
from .helpers import context, seed, prepare_dispatch

def test_confirmation_retains_draft_acceptance_and_assumptions(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path,confirm=False)
        req=store.get_revision(p["requirement"])["payload"]
        acc=store.get_revision(p["acceptance"])["payload"]
        assert req["confirmed_assumptions"]==["test isolation"]
        assert req["acceptance_refs"]==[p["acceptance"].to_dict()]
        assert acc["acceptance_items"]==[p["item"]]
        old=store.get_revision(type(p["requirement"]).from_dict(req["confirmed_from_ref"]))["payload"]
        assert "confirmed_assumptions" not in old
        assert store.get_head("requirement",p["requirement"].object_id,"draft")["revision_id"]=="rev-1"
    finally: store.close()

def test_dispatch_freezes_all_fields_and_only_becomes_ready(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path,strategies=("s1","s2"),confirm=False)
        assert store.get_revision(p["packet"])["payload"]==p["body"]
        assert store.get_head("execution_packet",p["packet"].object_id,"current") is None
        data={"draft_ref":p["packet"].to_dict(),"expected_baseline_digest":sha256_digest(p["body"])}
        receipt=DesignService(store).dispatch_confirm(context(store,"confirm"),data)
        assert receipt.status=="committed",receipt.error
        head=store.get_head("task",p["task"].object_id,"current")
        ref=type(p["task"])(store.project_id,"task",p["task"].object_id,head["revision_id"])
        assert store.get_revision(ref)["payload"]["phase"]=="dispatch_ready"
    finally: store.close()

@pytest.mark.parametrize("kind",["missing","foreign","digest","cas"])
def test_dispatch_refuses_invalid_baselines(tmp_path,kind):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path,confirm=False)
        svc=DesignService(store)
        if kind in ("missing","foreign"):
            body=deepcopy(p["body"])
            body["environment_ref"]["revision_id"]="rev-404"
            if kind=="foreign": body["environment_ref"]["project_id"]="proj-b"
            result=svc.dispatch_draft(context(store,"bad"),body)
        else:
            data={"draft_ref":p["packet"].to_dict(),"expected_baseline_digest":"f"*64 if kind=="digest" else sha256_digest(p["body"])}
            ctx=context(store,"bad")
            if kind=="cas":
                from dataclasses import replace
                ctx=replace(ctx,expected_heads=(ExpectedHead(p["packet"],"current","9"),))
            result=svc.dispatch_confirm(ctx,data)
        assert result.status=="rejected"
        assert result.error.code in {"REFERENCE_NOT_FOUND","SCOPE_MISMATCH","SNAPSHOT_CHANGED","STALE_REVISION"}
        assert store.get_head("execution_packet",p["packet"].object_id,"current") is None
    finally: store.close()

def test_rules_publish_records_preview_and_dispatch_revoke(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path)
        result=DesignService(store).dispatch_revoke(context(store,"revoke"),{"packet_ref":p["packet"].to_dict(),"reason":"reconsider"})
        assert result.status=="committed",result.error
        assert store.get_revision(result.object_refs[0])["payload"]["revoked"]
    finally: store.close()
