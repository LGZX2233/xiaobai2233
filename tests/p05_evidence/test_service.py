"""Evidence effects, approved restore, retained errors and exact source ownership."""
import hashlib
import json
from pathlib import Path
import pytest
from project_kernel.application.evidence_service import EvidenceService,IsolatedRestoreTarget
from project_kernel.application.delivery.service import DeliveryService
from project_kernel.application.environment_service import EnvironmentService,PythonEnvironmentProbe
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import ObjectRef
from project_kernel.contracts.errors import KernelError
from project_kernel.evidence.provider import FileEvidenceProvider
from project_kernel.evidence import ArtifactStorage,BundleExporter,ArchiveManifest
from project_kernel.data.queries.service import QueryService
from project_kernel.interfaces.rpc.ingest import SourceIngestBridge
from project_kernel.bootstrap import build_server
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch,seed,context
from p13_integration.auth_helpers import build_test_server
from p13_integration.test_closed_loop import call

def state(store,receipt):
    return QueryService(store).operation_status(receipt.operation_id)

def test_archive_partial_repair_and_lost_receipt_reconcile(tmp_path,monkeypatch):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        storage=ArtifactStorage(tmp_path/"artifacts")
        ref=storage.publish(storage.stage(b"evidence","text/plain"),"text/plain")
        manifest=ArchiveManifest("manifest","a"*64,("op-1",),(ref,),("good","flaky"))
        mr=seed(store,"archive_manifest","manifest",manifest.body())
        seed(store,"archive_status","task",{"manifest_ref":mr.to_dict(),"required_sinks":["good","flaky"],
            "sink_states":{},"source_flushed":True,"overall":"export_pending"})
        good=BundleExporter(tmp_path/"good",storage)
        flaky=BundleExporter(tmp_path/"flaky",storage)
        svc=EvidenceService(store,provider=FileEvidenceProvider(store,artifact_storage=storage,exporters={"good":good,"flaky":flaky}))
        good_r=svc.archive_export(context(store,"good"),{"manifest_ref":mr.to_dict(),"sink_id":"good"})
        assert state(store,good_r)["status"]=="succeeded"
        original=flaky.export
        calls=[]
        def failed(*args,**kwargs):
            calls.append(1)
            raise OSError("sink disconnected")
        monkeypatch.setattr(flaky,"export",failed)
        broken=svc.archive_export(context(store,"broken"),{"manifest_ref":mr.to_dict(),"sink_id":"flaky"})
        assert state(store,broken)["status"]=="unknown"
        assert svc.archive_export(context(store,"broken"),{"manifest_ref":mr.to_dict(),"sink_id":"flaky"})==broken
        assert len(calls)==1
        assert QueryService(store).latest_revisions("archive_status")[0]["payload"]["overall"]=="partial"
        monkeypatch.setattr(flaky,"export",original)
        repaired=svc.archive_repair(context(store,"repair"),{"manifest_ref":mr.to_dict(),"sink_id":"flaky","original_effect_id":broken.operation_id})
        assert state(store,repaired)["status"]=="succeeded"
        assert QueryService(store).latest_revisions("archive_status")[0]["payload"]["overall"]=="complete"
        # A new manifest effect commits bytes but loses its settlement.
        mr2=seed(store,"archive_manifest","manifest2",ArchiveManifest("manifest2","b"*64,(),(ref,),("good",)).body())
        settle=svc._settle
        monkeypatch.setattr(svc,"_settle",lambda *a,**k:None)
        lost=svc.archive_export(context(store,"lost"),{"manifest_ref":mr2.to_dict(),"sink_id":"good"})
        monkeypatch.setattr(svc,"_settle",settle)
        assert svc.reconcile(context(store,"reconcile"),lost.operation_id)["status"]=="succeeded"
    finally:store.close()

def test_artifact_ingest_requires_bound_stream_and_preserves_gap(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        storage=ArtifactStorage(tmp_path/"artifacts")
        source=seed(store,"source","host",{"host_id":"host"})
        policy=seed(store,"retention","retain",{"mode":"test"})
        srv=build_test_server(store,artifact_root=tmp_path/"artifacts",
            evidence_config={"trusted_staging_principals":["user-1"]},
            source_bindings={"user-1":[("host","session","1")]})
        events=[]
        for seq in (2,1):
            body={"text":"source "+str(seq)}
            raw=json.dumps(body).encode()
            staged=storage.stage(raw,"application/json")
            locator=seed(store,"staging","stage-"+str(seq),{"locator":staged.staged_locator,"digest":staged.sha256})
            receipt=call(srv,"proj-a","artifact.register",{"trusted_staged_locator_ref":locator.to_dict(),
                "digest":staged.sha256,"source_ref":source.to_dict(),"media_type":"application/json",
                "retention_policy_ref":policy.to_dict()},"register-"+str(seq))
            operation=call(srv,"proj-a","operation.status",{"operation_id":receipt["operation_id"]},query=True)["data"]
            assert operation["status"]=="succeeded",operation
            event={"source_seq":str(seq),"payload_hash":sha256_digest(body),"schema_version":"1.0.0",
                "payload_artifact_ref":store.get_revision(ObjectRef.from_dict(operation["result_refs"][0]))["payload"]["artifact"],"evidence_mode":"test"}
            events.append(event)
            payload={"source_stream":{"host_id":"host","origin_session_id":"session","log_generation":"1"},
                "events":[event],"observed_range":{"first":str(seq),"last":str(seq),"truncated":False}}
            receipt=call(srv,"proj-a","source.ingest",payload,"ingest-"+str(seq))
            assert call(srv,"proj-a","source.ingest",payload,"ingest-"+str(seq))==receipt
            cursor=store.conn.execute("SELECT contiguous_seq FROM source_cursor").fetchone()[0]
            assert cursor==("0" if seq==2 else "2")
        rogue=build_test_server(store,artifact_root=tmp_path/"artifacts",source_bindings={})
        from project_kernel.interfaces.rpc.framing import encode_frame,decode_frame
        response=decode_frame(rogue.handle_line(encode_frame({"jsonrpc":"2.0","id":"x","method":"kernel.command","params":{
            "protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-a"},
            "command":"source.ingest","payload":payload,"expected_heads":[],"idempotency_key":"rogue"}})))
        assert response["error"]["data"]["code"]=="PERMISSION_DENIED"
    finally:store.close()

def test_environment_versions_missing_and_old_are_retained(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        p=prepare_dispatch(store,tmp_path)
        recipe=seed(store,"recipe","probe",{"dependencies":[{"name":"python","version_spec":">=999"},
            {"name":"dsh-impossible-missing-distribution-1009","version_spec":">=1"}]})
        svc=EnvironmentService(store,PythonEnvironmentProbe())
        data={"task_ref":p["task"].to_dict(),"execution_root_ref":p["roots"]["s1"].to_dict(),
            "requirement_refs":[p["requirement"].to_dict()],"recipe_refs":[recipe.to_dict()]}
        receipt=svc.environment_probe(context(store,"probe"),data)
        result=state(store,receipt)
        assert {f["state"] for f in result["facts"]}=={"too_old","missing"}
        assert result["facts"][0]["version"] and result["facts"][0]["path"]
        assert QueryService(store).environment_report(p["task"].to_dict())["data"]["too_old"]
    finally:store.close()

def test_restore_refuses_an_unapproved_target_and_busy_fence(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        storage=ArtifactStorage(tmp_path/"artifacts")
        svc=EvidenceService(store,provider=FileEvidenceProvider(store,artifact_storage=storage,backup_root=tmp_path/"backups",
            restore_target=IsolatedRestoreTarget(tmp_path/"restore","one")))
        sr=seed(store,"store","store-a",{"store_id":"store-a"})
        policy=seed(store,"policy","backup",{})
        backup=svc.backup_create(context(store,"backup"),{"store_ref":sr.to_dict(),"policy_ref":policy.to_dict()})
        bref=state(store,backup)["result_refs"][0]
        plan=svc.restore_plan(context(store,"plan"),{"revision_or_backup_ref":bref,"restore_kind":"disaster_recovery","reason":"test"})
        pref=plan.object_refs[0]
        row=store.get_revision(pref)
        target=seed(store,"restore_target","other",{"target_id":"two","target_scope":"project"})
        decision=DeliveryService(store).decision_record(context(store,"decision"),{"subject_kind":"restore_plan",
            "subject_ref":pref.to_dict(),"subject_digest":row["digest"],"action":"restore.apply","target_scope":"project",
            "target_ref":target.to_dict(),"decision":"approved","reason":"wrong target"},is_human=True)
        with pytest.raises(KernelError):
            svc.restore_apply(context(store,"restore"),{"restore_plan_ref":pref.to_dict(),"human_decision_ref":decision.object_refs[0].to_dict()})
        assert not (tmp_path/"restore").exists()
        good=DeliveryService(store).decision_record(context(store,"good-decision"),{"subject_kind":"restore_plan",
            "subject_ref":pref.to_dict(),"subject_digest":row["digest"],"action":"restore.apply","target_scope":"project",
            "target_ref":row["payload"]["target_ref"],"decision":"approved","reason":"correct target"},is_human=True)
        with svc.provider.restore_target.fence():
            blocked=svc.restore_apply(context(store,"busy"),{"restore_plan_ref":pref.to_dict(),"human_decision_ref":good.object_refs[0].to_dict()})
            assert state(store,blocked)["status"]=="unknown"
        assert not list((tmp_path/"restore").glob("*.sqlite"))
    finally:store.close()
