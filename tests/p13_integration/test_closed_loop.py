"""Public-entry dual-strategy workflow; only host-owned configuration is seeded."""
import hashlib
import json
import sys
from pathlib import Path
import pytest
from project_kernel.bootstrap import build_server
from project_kernel.contracts import sha256_digest, ALL_CAPABILITIES
from project_kernel.contracts.dto import ObjectRef, CheckResult
from project_kernel.application.environment_service import PythonEnvironmentProbe
from project_kernel.application.evidence_service import EvidenceService, IsolatedRestoreTarget
from project_kernel.evidence import ArtifactStorage, BundleExporter
from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, seed, context
from p03_attempt.fixture_executor import FixtureSubprocessExecutor
from .auth_helpers import build_test_server

def call(server,project,name,payload,key=None,query=False,**extra):
    params={"protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":project},"payload":payload}
    if query: params["query"]=name
    else: params.update(command=name,idempotency_key=key or name,expected_heads=[])
    params.update(extra)
    response=decode_frame(server.handle_line(encode_frame({"jsonrpc":"2.0","id":"r1",
        "method":"kernel.query" if query else "kernel.command","params":params})))
    assert "error" not in response,(name,response)
    if query: return response["result"]
    result=response["result"]["receipt"]
    assert result["status"]!="rejected",(name,result)
    return result

def latest(store,kind,oid):
    return ObjectRef(store.project_id,kind,oid,store.get_head(kind,oid,"current")["revision_id"])

class RecordedExecutor(FixtureSubprocessExecutor):
    def __init__(self):
        super().__init__({"s1":[sys.executable,"-c","raise SystemExit(7)"],
                         "s2":[sys.executable,"-c","from pathlib import Path; Path('output.txt').write_text('verified'); print('ok')"]})
        self.calls=0
    def run(self,*args):
        self.calls+=1
        return super().run(*args)

class FileCheckProvider:
    def __init__(self,store,storage):
        self.store=store
        self.storage=storage
        self.calls=0
    def run(self,scope,attempt,candidate,acceptance_refs):
        assert not self.store.conn.in_transaction
        self.calls+=1
        body=self.store.get_revision(candidate)["payload"]
        artifacts=body["artifacts"]
        from project_kernel.contracts.dto import ArtifactRef
        valid=bool(artifacts) and all(self.storage.open_read(ArtifactRef(**a)) in {b"verified",b"verified revision two"} for a in artifacts)
        items=self.store.get_revision(ObjectRef.from_dict(acceptance_refs[0]))["payload"]["acceptance_items"]
        return tuple(CheckResult(i["item_id"],ObjectRef.from_dict(i["recipe_ref"]),result="pass" if valid else "fail",
            candidate_digest=body["candidate_digest"],evidence_mode="test") for i in items)

def test_dual_project_workflow_delivery_archive_and_offline_restore(tmp_path,monkeypatch):
    root=tmp_path/"A"
    root.mkdir()
    store=make_store(root,project_id="proj-a")
    b_root=tmp_path/"B"
    b_root.mkdir()
    other=make_store(b_root,project_id="proj-b")
    storage=ArtifactStorage(root/"artifacts")
    exporter=BundleExporter(root/"exports",storage,allowed_sinks=("exports",))
    exe=RecordedExecutor()
    checks=FileCheckProvider(store,storage)
    config={"exporters":{"exports":exporter},"backup_root":root/"backups",
            "restore_target":IsolatedRestoreTarget(root/"restore","offline")}
    srv=build_test_server(store,executor=exe,artifact_root=root/"artifacts",bundle_exporter=exporter,
        environment_provider=PythonEnvironmentProbe(),check_provider=checks,evidence_config=config)
    human=build_test_server(store,human=True)
    invoke=lambda name,body,key: call(srv,"proj-a",name,body,key)
    try:
        p=prepare_dispatch(store,root,strategies=("s1","s2"),invoke=invoke)
        other_server=build_test_server(other)
        call(other_server,"proj-b","task.create",{"title":"isolated task","goal":"same display name","requirement_refs":[],"mode":"test"})
        denied=decode_frame(srv.handle_line(encode_frame({"jsonrpc":"2.0","id":"r2","method":"kernel.query","params":{
            "protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-b"},
            "query":"project.overview","payload":{}}})))
        assert denied["error"]["data"]["code"]=="SCOPE_MISMATCH"
        def start(strategy,key):
            data={"packet_ref":p["packet"].to_dict(),"strategy_id":strategy,"execution_root_ref":p["roots"][strategy].to_dict()}
            receipt=invoke("attempt.start",data,key)
            assert invoke("attempt.start",data,key)==receipt
            return latest(store,"attempt",receipt["operation_id"])
        failed=start("s1","first-failure")
        failed_payload=store.get_revision(failed)["payload"]
        assert failed_payload["status"]=="failed" and failed_payload["exit_code"]==7
        assert failed_payload["output_artifacts"]["stderr"]["sha256"]
        exe.command_map["s1"]=exe.command_map["s2"]
        repaired=start("s1","repair-attempt")
        alternative=start("s2","alternative")
        assert exe.calls==3
        candidates=[]
        reports=[]
        for index,attempt in enumerate((repaired,alternative)):
            raw=(root/f"s{index+1}"/"output.txt").read_bytes()
            artifact=storage.publish(storage.stage(raw,"text/plain"),"text/plain")
            candidate=seed(store,"candidate_manifest","candidate-"+str(index),
                {"attempt_ref":attempt.to_dict(),"candidate_digest":hashlib.sha256(raw).hexdigest(),
                 "artifacts":[artifact.to_dict()]})
            data={"attempt_ref":attempt.to_dict(),"candidate_manifest_ref":candidate.to_dict(),
                  "acceptance_refs":[p["acceptance"].to_dict()]}
            receipt=invoke("verification.run",data,"verify-"+str(index))
            assert invoke("verification.run",data,"verify-"+str(index))==receipt
            assert store.get_revision(ObjectRef.from_dict(receipt["object_refs"][0]))["payload"]["passed"]
            candidates.append(candidate)
            reports.append(receipt["object_refs"][0])
        assert checks.calls==2
        comparison=call(srv,"proj-a","attempts.compare",{"task_ref":p["task"].to_dict()},query=True)
        assert comparison["data"]
        selection=invoke("attempt.select",{"attempt_ref":repaired.to_dict(),
            "comparison_refs":[failed.to_dict(),repaired.to_dict(),alternative.to_dict()],"purpose":"delivery",
            "reason":"choose repaired first strategy; second retained for comparison"},"select")["object_refs"][0]
        target=seed(store,"delivery_target","bundle",{"method":"bundle","sink_id":"exports"})
        request=invoke("delivery.request",{"selection_ref":selection,"candidate_ref":candidates[0].to_dict(),
            "target_ref":target.to_dict()},"request")
        approval=store.get_revision(ObjectRef.from_dict(request["object_refs"][0]))["payload"]
        assert approval["status"]=="pending"
        payload={"approval_id":approval["approval_id"],"snapshot_digest":approval["snapshot_digest"],"decision":"approved","reason":"reviewed isolated files"}
        refused=decode_frame(srv.handle_line(encode_frame({"jsonrpc":"2.0","id":"x","method":"kernel.command","params":{
            "protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-a"},
            "command":"approval.decide","payload":payload,"expected_heads":[],"idempotency_key":"machine-approve"}})))
        assert refused["error"]["data"]["code"]=="UNSUPPORTED_COMMAND"
        call(human,"proj-a","approval.decide",payload,"approve")
        old_approval=dict(approval)
        changed=b"verified revision two"
        changed_artifact=storage.publish(storage.stage(changed,"text/plain"),"text/plain")
        candidate=seed(store,"candidate_manifest",candidates[0].object_id,
            {"attempt_ref":repaired.to_dict(),"candidate_digest":hashlib.sha256(changed).hexdigest(),
             "artifacts":[changed_artifact.to_dict()]})
        invoke("verification.run",{"attempt_ref":repaired.to_dict(),"candidate_manifest_ref":candidate.to_dict(),
            "acceptance_refs":[p["acceptance"].to_dict()]},"verify-changed")
        old=store.get_revision(latest(store,"approval",old_approval["approval_id"]))["payload"]
        assert old["status"]=="superseded"
        selection=invoke("attempt.select",{"attempt_ref":repaired.to_dict(),
            "comparison_refs":[failed.to_dict(),repaired.to_dict(),alternative.to_dict()],"purpose":"delivery",
            "reason":"reverified candidate selected; alternative retained"},"select-changed")["object_refs"][0]
        request=invoke("delivery.request",{"selection_ref":selection,"candidate_ref":candidate.to_dict(),
            "target_ref":target.to_dict()},"request-changed")
        approval=store.get_revision(ObjectRef.from_dict(request["object_refs"][0]))["payload"]
        call(human,"proj-a","approval.decide",{"approval_id":approval["approval_id"],
            "snapshot_digest":approval["snapshot_digest"],"decision":"approved","reason":"reviewed changed candidate"},"approve-changed")
        from project_kernel.data.store.uow import UnitOfWork
        execute=UnitOfWork.execute
        def lose_settlement(self,callback):
            if self.command_kind=="delivery.settle":
                raise OSError("test: effect landed before settlement loss")
            return execute(self,callback)
        monkeypatch.setattr(UnitOfWork,"execute",lose_settlement)
        data={"approval_id":approval["approval_id"],"snapshot_digest":approval["snapshot_digest"]}
        lost=decode_frame(srv.handle_line(encode_frame({"jsonrpc":"2.0","id":"lost","method":"kernel.command","params":{
            "protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-a"},
            "command":"delivery.apply","payload":data,"expected_heads":[],"idempotency_key":"apply"}})))
        assert lost["error"]["data"]["code"]=="TEMPORARY_UNAVAILABLE"
        monkeypatch.setattr(UnitOfWork,"execute",execute)
        original_export=exporter.export
        monkeypatch.setattr(exporter,"export",lambda *a,**k:pytest.fail("delivery must not execute twice"))
        applied=invoke("delivery.apply",data,"apply")
        invoke("delivery.reconcile",{"operation_id":applied["operation_id"]},"reconcile")
        monkeypatch.setattr(exporter,"export",original_export)
        op=call(srv,"proj-a","operation.status",{"operation_id":applied["operation_id"]},query=True)["data"]
        assert op["status"]=="applied"
        operation=latest(store,"delivery",applied["operation_id"])
        closed=invoke("task.close",{"task_ref":p["task"].to_dict(),"applied_operation_ref":operation.to_dict()},"close")
        manifest=closed["object_refs"][1]
        from project_kernel.evidence.archive import SinkReceipt
        monkeypatch.setattr(exporter,"export",lambda m,s,**kw:
            SinkReceipt(m.manifest_id,s,"failed",m.digest(),error="test sink offline"))
        failed_archive=invoke("archive.export",{"manifest_ref":manifest,"sink_id":"exports"},"archive-failed")
        status=call(srv,"proj-a","archive.status",{"manifest_ref":manifest},query=True)["data"]
        assert "partial" in json.dumps(status)
        monkeypatch.setattr(exporter,"export",original_export)
        exported=invoke("archive.repair",{"manifest_ref":manifest,"sink_id":"exports",
            "original_effect_id":failed_archive["operation_id"]},"archive-recover")
        estate=call(srv,"proj-a","operation.status",{"operation_id":exported["operation_id"]},query=True)["data"]
        assert estate["status"]=="succeeded",estate
        bundle=root/"exports"/manifest["object_id"]
        assert (bundle/"manifest.json").is_file()
        artifact_path=next((bundle/"artifacts").iterdir())
        expected_bytes=artifact_path.read_bytes()
        artifact_path.unlink()
        repaired_archive=invoke("archive.repair",{"manifest_ref":manifest,"sink_id":"exports",
            "original_effect_id":exported["operation_id"]},"archive-repair")
        assert artifact_path.read_bytes()==expected_bytes and exe.calls==3
        assert call(srv,"proj-a","operation.status",{"operation_id":repaired_archive["operation_id"]},query=True)["data"]["status"]=="succeeded"
        from p07_migration.helpers import make_legacy_source, PROJECT_MAPPING
        from project_kernel.migration.legacy import LegacyImportService
        legacy=make_legacy_source(root)
        source_hash=hashlib.sha256((legacy/"legacy.sqlite").read_bytes()).hexdigest()
        migration=LegacyImportService(store,legacy,root/"quarantine","legacy-store","proj-a",PROJECT_MAPPING,batch_id="ac43")
        imported=migration.import_batch()
        assert imported.imported>0
        assert migration.import_batch().imported==0
        assert hashlib.sha256((legacy/"legacy.sqlite").read_bytes()).hexdigest()==source_hash
        store_ref=seed(store,"store",store.store_id,{"store_id":store.store_id})
        policy_ref=seed(store,"backup_policy","policy",{"mode":"test"})
        backup=invoke("backup.create",{"store_ref":store_ref.to_dict(),"policy_ref":policy_ref.to_dict()},"backup")
        backup_op=call(srv,"proj-a","operation.status",{"operation_id":backup["operation_id"]},query=True)["data"]
        assert backup_op["status"]=="succeeded",backup_op
        plan=invoke("restore.plan",{"revision_or_backup_ref":backup_op["result_refs"][0],
            "restore_kind":"disaster_recovery","reason":"isolated WAL restore rehearsal"},"restore-plan")
        plan_ref=ObjectRef.from_dict(plan["object_refs"][0])
        plan_row=store.get_revision(plan_ref)
        decision=call(human,"proj-a","decision.record",{"subject_kind":"restore_plan","subject_ref":plan_ref.to_dict(),
            "subject_digest":plan_row["digest"],"action":"restore.apply","target_scope":"project",
            "target_ref":plan_row["payload"]["target_ref"],"decision":"approved","reason":"offline isolated rehearsal"},"restore-decision")
        restored=invoke("restore.apply",{"restore_plan_ref":plan_ref.to_dict(),"human_decision_ref":decision["object_refs"][0]},"restore")
        restored_op=call(srv,"proj-a","operation.status",{"operation_id":restored["operation_id"]},query=True)["data"]
        assert restored_op["status"]=="succeeded",restored_op
        import sqlite3
        copied=sqlite3.connect(restored_op["restored_path"])
        try:
            assert copied.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            assert copied.execute("SELECT COUNT(*) FROM revision WHERE type='attempt'").fetchone()[0]>=9
        finally: copied.close()
        assert store.get_revision(failed)["payload"]["status"]=="failed"
        final_seq=str(store.next_commit_seq()-1)
        store.close()
        store=make_store(root,project_id="proj-a")
        restarted=build_test_server(store)
        historical=call(restarted,"proj-a","project.overview",{},query=True,as_of_seq=final_seq)
        assert historical["data"]["phases"]["closed"]==1
        assert call(restarted,"proj-a","events.read",{"after":{"commit_seq":final_seq,"event_index":999},"limit":100},query=True)["data"]==[]
        (tmp_path/"scenario-evidence.json").write_text(json.dumps({"provider_calls":exe.calls,"check_calls":checks.calls,
            "source_seq":final_seq,"restored_path":restored_op["restored_path"],"failed_attempt":failed.to_dict(),
            "manifest":manifest,"legacy_source_sha256":source_hash,"legacy_imported":imported.imported,
            "old_approval":old_approval["approval_id"],"new_approval":approval["approval_id"],
            "delivery_operation_id":applied["operation_id"],"archive_repaired":True},indent=2),encoding="utf-8")
    finally:
        store.close()
        other.close()
