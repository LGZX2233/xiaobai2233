"""Exclusive writer fencing and real replacement, only in pytest temporary roots."""
from pathlib import Path
import json
import os
import subprocess
import sys
import pytest
from project_kernel.application.evidence_service import EvidenceService
from project_kernel.application.delivery.service import DeliveryService
from project_kernel.application.recovery_authorization import authorize_restore
from project_kernel.evidence.provider import FileEvidenceProvider
from project_kernel.evidence import ArtifactStorage
from project_kernel.evidence.recovery import ControlledStoreRecovery, ControlledStoreRestoreTarget
from project_kernel.data.store.access_fence import ProjectAccessFence
from project_kernel.data.store.store import Store
from project_kernel.contracts.errors import KernelError
from p01_store.helpers import make_store
from p02_design.helpers import context, seed
from p05_evidence.test_service import state


def prepare(tmp_path):
    store=make_store(tmp_path)
    storage=ArtifactStorage(tmp_path/"artifacts")
    live=tmp_path/"proj-a.sqlite"
    target=ControlledStoreRestoreTarget(live,"controlled-test")
    service=EvidenceService(store,provider=FileEvidenceProvider(store,artifact_storage=storage,backup_root=tmp_path/"backups",restore_target=target))
    original=seed(store,"requirement","before",{"title":"committed WAL before backup"})
    sr=seed(store,"store","store-a",{"store_id":"store-a"})
    policy=seed(store,"policy","backup",{})
    backup=service.backup_create(context(store,"backup"),{"store_ref":sr.to_dict(),"policy_ref":policy.to_dict()})
    bref=state(store,backup)["result_refs"][0]
    plan=service.restore_plan(context(store,"plan"),{"revision_or_backup_ref":bref,
        "restore_kind":"disaster_recovery","reason":"temporary maintenance test"})
    row=store.get_revision(plan.object_refs[0])
    decision=DeliveryService(store).decision_record(context(store,"approve"),{
        "subject_kind":"restore_plan","subject_ref":plan.object_refs[0].to_dict(),"subject_digest":row["digest"],
        "action":"restore.apply","target_scope":"project","target_ref":row["payload"]["target_ref"],
        "decision":"approved","reason":"replace isolated test store and preserve subsequent history"},is_human=True)
    later=seed(store,"requirement","after",{"title":"history after backup"})
    payload={"restore_plan_ref":plan.object_refs[0].to_dict(),"human_decision_ref":decision.object_refs[0].to_dict()}
    scope=context(store,"maintenance").scope
    recovery=ControlledStoreRecovery(target,project_id="proj-a",store_id="store-a",
        backup_root=tmp_path/"backups",audit_root=tmp_path/"maintenance-audit",artifact_storage=storage,
        authorize_restore=authorize_restore)
    return store,service,recovery,payload,scope,original,later


def test_real_restore_blocks_live_writers_and_preserves_post_backup_history(tmp_path):
    store,service,recovery,payload,scope,original,later=prepare(tmp_path)
    with pytest.raises(KernelError) as busy:
        recovery.apply(scope,payload,"restore")
    assert busy.value.error.code=="TEMPORARY_UNAVAILABLE"
    rpc=service.restore_apply(context(store,"rpc-refuse"),payload)
    assert rpc.status=="rejected" and rpc.error.code=="CAPABILITY_UNAVAILABLE"
    store.close()
    result=recovery.apply(scope,payload,"restore")
    assert result["status"]=="succeeded" and result["writer_fence_held"]
    assert recovery.apply(scope,payload,"restore")==result
    restored=make_store(tmp_path)
    try:
        assert restored.get_revision(original)
        assert restored.get_revision(later) is None
    finally:restored.close()
    historical=Store.open_project(Path(result["history_backup"]["backup_path"]),"proj-a","store-a",read_only=True)
    try:assert historical.get_revision(later)
    finally:historical.close()
    assert json.loads((Path(result["audit_path"])/"intent.json").read_text())["payload"]==payload
    assert Path(result["original_path"]).exists()


def test_fence_blocks_new_writer_in_another_process(tmp_path):
    store=make_store(tmp_path)
    store.close()
    code="""import sys
from pathlib import Path
from project_kernel.data.store.store import Store
from project_kernel.contracts.errors import KernelError
try:
    store=Store.open_project(Path(sys.argv[1]),'proj-a','store-a')
except KernelError as exc:
    assert exc.error.code=='TEMPORARY_UNAVAILABLE'
    print('blocked')
else:
    store.close()
    raise AssertionError('writer bypassed maintenance fence')
"""
    environment={key:value for key,value in os.environ.items() if key.upper() in {"SYSTEMROOT","WINDIR","PATH","TEMP","TMP"}}
    environment["PYTHONPATH"]=str(Path(__file__).resolve().parents[2]/"src")
    with ProjectAccessFence(tmp_path/"proj-a.sqlite",exclusive=True):
        child=subprocess.run([sys.executable,"-B","-c",code,str(tmp_path/"proj-a.sqlite")],
            capture_output=True,text=True,timeout=10,env=environment)
        assert child.returncode==0,child.stderr
        assert child.stdout.strip()=="blocked"
    store=make_store(tmp_path)
    store.close()


def test_failed_post_restore_verification_restores_original_and_keeps_audit(tmp_path,monkeypatch):
    store,_,recovery,payload,scope,original,later=prepare(tmp_path)
    store.close()
    verify=recovery._verify
    def fail_published(path,source_conn=None):
        if Path(path)==tmp_path/"proj-a.sqlite":
            raise OSError("post-restore verifier unavailable")
        return verify(path,source_conn)
    monkeypatch.setattr(recovery,"_verify",fail_published)
    with pytest.raises(OSError):
        recovery.apply(scope,payload,"fail")
    reopened=make_store(tmp_path)
    try:
        assert reopened.get_revision(original)
        assert reopened.get_revision(later)
    finally:reopened.close()
    failures=list((tmp_path/"maintenance-audit").glob("*/failure.json"))
    assert len(failures)==1
    assert list(failures[0].parent.glob("failed-restored.sqlite"))


def test_lost_recovery_receipt_reconciles_without_replacement(tmp_path,monkeypatch):
    store,_,recovery,payload,scope,original,later=prepare(tmp_path)
    store.close()
    result=recovery.apply(scope,payload,"lost")
    receipt=Path(result["audit_path"])/"receipt.json"
    receipt.rename(receipt.with_name("lost-receipt.json"))
    with pytest.raises(KernelError):
        recovery.apply(scope,payload,"lost")
    live=Path(result["restored_path"])
    before=live.stat().st_mtime_ns
    reconciled=recovery.reconcile(scope,payload,"lost")
    assert reconciled["status"]=="succeeded" and reconciled["reconciled"]
    assert live.stat().st_mtime_ns==before
    assert recovery.apply(scope,payload,"lost")==reconciled
