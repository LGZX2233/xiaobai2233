"""Durable evidence operations with filesystem effects outside write transactions."""
from __future__ import annotations
import json
import uuid
from ..contracts import sha256_digest
from ..contracts.dto import ArtifactRef, CommandContext, ObjectRef
from ..contracts.errors import KernelError, invalid_input, capability_unavailable, permission_denied, artifact_digest_mismatch
from ..data.store.uow import UnitOfWork
from ..data.queries.service import QueryService
from ..evidence import ArchiveManifest
from ..evidence.provider import IsolatedRestoreTarget  # Compatibility import for configured callers.
from ..internal.provider_ports import EvidenceEffects
from .recovery_authorization import authorized_restore_inputs
from .security import require_scope
from .design.references import checked_payload, exact

_EFFECT_RESULT_FIELDS = frozenset({
    "status", "error", "restored_path", "file_sha256", "writer_fence_held", "mode",
    "original_store_preserved", "reconciled",
})


class EvidenceService:
    """Authorize evidence requests and settle effects from an injected provider."""

    def __init__(self, store, *, provider: EvidenceEffects | None = None,
                 trusted_staging_principals=()):
        self.store = store
        self.provider = provider
        self.trusted_staging_principals = frozenset(trusted_staging_principals)

    def _publish(self,h,kind,oid,body):
        head=self.store.get_head(kind,oid,"current")
        ref=h.records.append_revision(kind,oid,body,kind+".v1")
        h.records.publish_head(ref,"current",str(head["head_version"]) if head else None)
        return ref

    def _operation(self,operation_id):
        head=self.store.get_head("evidence_operation",operation_id,"current")
        if not head:
            raise KernelError(invalid_input("evidence operation not found"))
        return exact(self.store,ObjectRef(self.store.project_id,"evidence_operation",operation_id,head["revision_id"]))[1]["payload"]

    def _run(self,ctx,command,payload,capability,prepare,effect):
        require_scope(self.store,ctx.scope,capability)
        state={}
        def cb(h):
            data=checked_payload(command,payload)
            pinned=prepare(data)
            oid="evidence-"+uuid.uuid4().hex[:20]
            body={"operation_id":oid,"command":command,"status":"claimed","epoch":"1",
                  "principal_id":ctx.scope.principal_id,"payload":data,"pinned":pinned}
            ref=self._publish(h,"evidence_operation",oid,body)
            h.outbox.enqueue("evidence",oid,command,json.dumps(ref.to_dict()))
            lease=h.outbox.claim("evidence",oid,command)
            state.update(body=body,lease=lease)
            h.outcome.object_refs=(ref,)
            h.outcome.operation_id=oid
        uow=UnitOfWork(self.store,ctx,command)
        receipt=uow.execute(cb)
        if receipt.status!="accepted" or not uow.did_commit:
            return receipt
        try:
            result=effect(state["body"])
        except Exception as exc:
            result={"status":"unknown","error":{"type":type(exc).__name__,"message":str(exc)}}
        self._settle(ctx,receipt.operation_id,result,state["lease"])
        return receipt

    def _settle(self,ctx,oid,result,lease=None):
        """Publish provider observations without changing the claimed operation identity."""
        observed={key:value for key,value in result.items() if key in _EFFECT_RESULT_FIELDS}
        if observed.get("status") not in {"succeeded","failed","unknown"}:
            observed["status"]="unknown"
        def cb(h):
            body=self._operation(oid)
            if body["status"] in {"succeeded","failed"}:
                return
            refs=[]
            details={}
            expected_type={"artifact.register":"artifact","backup.create":"backup_manifest"}.get(body["command"])
            if expected_type is not None and result.get("object_type")==expected_type:
                refs.append(self._publish(h,expected_type,oid,result["body"]))
                details.update(object_type=expected_type,body=result["body"])
            sink=result.get("sink_receipt") if body["command"].startswith("archive.") else None
            if body["command"].startswith("archive.") and (sink is not None or observed["status"]=="succeeded"):
                manifest=body["pinned"]["manifest"]
                valid=(isinstance(sink,dict) and sink.get("sink_id")==body["payload"]["sink_id"]
                    and sink.get("manifest_id")==manifest["manifest_id"]
                    and sink.get("digest")==sha256_digest(manifest)
                    and sink.get("state") in {"succeeded","failed","unknown"}
                    and sink.get("state")==observed["status"]
                    and (sink["state"]!="succeeded" or sink.get("verified") is True))
                if not valid:
                    observed.update(status="unknown",error={"type":"ProviderReceiptMismatch",
                        "message":"archive receipt identity, digest, state or verification differs"})
                    sink=None
            if sink:
                details["sink_receipt"]=sink
            ref=self._publish(h,"evidence_operation",oid,{**body,**observed,**details,
                "provider_result":result,"result_refs":[r.to_dict() for r in refs]})
            if lease:
                if observed["status"]=="succeeded":
                    h.outbox.ack(lease["outbox_id"],lease["lease_token"])
                else:
                    h.outbox.fail(lease["outbox_id"],lease["lease_token"],json.dumps(observed.get("error",{})))
            if sink:
                self._record_archive(h,body["payload"]["manifest_ref"],sink)
            h.outcome.object_refs=(ref,*refs)
        derived=CommandContext(ctx.scope,ctx.command_id,oid+":settle:"+sha256_digest(result)[:16],sha256_digest(result))
        receipt=UnitOfWork(self.store,derived,"evidence.settle").execute(cb)
        if receipt.status=="rejected": raise KernelError(receipt.error)
        return receipt

    def _record_archive(self,h,manifest_ref,sink):
        for row in QueryService(self.store).latest_revisions("archive_status"):
            body=row["payload"]
            if body.get("manifest_ref")!=manifest_ref: continue
            from ..domain.delivery import archive_overall
            states={**body.get("sink_states",{}),sink["sink_id"]:sink["state"]}
            from ..data.queries.watermarks import ReadEnvelope
            watermarks=ReadEnvelope(self.store.conn,self.store.project_id,self.store.store_id).source_watermarks()
            requested=body.get("source_collection_requested",body.get("source_flushed",False))
            flushed=requested is True and watermarks["data_state"] in {"ok","no_data"}
            overall=archive_overall(body["required_sinks"],states,source_flushed=flushed)
            self._publish(h,"archive_status",row["object_id"],{**body,"sink_states":states,"overall":overall,
                "source_flushed":flushed,"source_watermarks":watermarks,
                "source_check_seq":str(h.records.commit_seq),"source_flush_basis":"local_observation_only",
                "receipts":{**body.get("receipts",{}),sink["sink_id"]:{**sink,"recorded_seq":str(h.records.commit_seq)}}})

    def artifact_register(self,ctx,payload):
        def prepare(data):
            if self.provider is None or not self.provider.artifact_available: raise KernelError(capability_unavailable("artifact storage unavailable"))
            _,staged=exact(self.store,data["trusted_staged_locator_ref"],"staging")
            if staged["principal_id"] not in self.trusted_staging_principals:
                raise KernelError(permission_denied("staging locator is not from a trusted producer"))
            exact(self.store,data["source_ref"])
            exact(self.store,data["retention_policy_ref"])
            body=staged["payload"]
            if body["digest"]!=data["digest"]:
                raise KernelError(artifact_digest_mismatch("staged digest differs"))
            return body
        def effect(op):
            data=op["payload"]
            artifact=self.provider.register_artifact(op["pinned"],data)
            return {"status":"succeeded","object_type":"artifact","body":{"artifact":artifact,"source_ref":data["source_ref"],
                     "retention_policy_ref":data["retention_policy_ref"]}}
        return self._run(ctx,"artifact.register",payload,"system.ingest",prepare,effect)

    def _manifest(self,raw):
        _,row=exact(self.store,raw,"archive_manifest")
        body=row["payload"]
        return ArchiveManifest(body["manifest_id"],body["snapshot_digest"],tuple(body["delivery_operation_refs"]),
            tuple(ArtifactRef(**a) for a in body["artifacts"]),tuple(body["required_sinks"]))

    def _archive(self,ctx,payload,repair):
        command="archive.repair" if repair else "archive.export"
        def prepare(data):
            manifest=self._manifest(data["manifest_ref"])
            if (self.provider is None or data["sink_id"] not in manifest.required_sinks
                    or data["sink_id"] not in self.provider.sink_ids):
                raise KernelError(capability_unavailable("archive sink is not configured or required"))
            if repair:
                original=self._operation(data["original_effect_id"])
                if (original["command"] not in {"archive.export","archive.repair"} or
                    original["payload"]["manifest_ref"]!=data["manifest_ref"] or
                    original["payload"]["sink_id"]!=data["sink_id"]):
                    raise KernelError(invalid_input("repair must refer to the original manifest and sink"))
            return {"manifest":manifest.body()}
        def effect(op):
            data=op["payload"]
            body=op["pinned"]["manifest"]
            manifest=ArchiveManifest(body["manifest_id"],body["snapshot_digest"],tuple(body["delivery_operation_refs"]),
                tuple(ArtifactRef(**a) for a in body["artifacts"]),tuple(body["required_sinks"]))
            sink=self.provider.archive(manifest,data["sink_id"],op["operation_id"],repair=repair,
                original_effect_id=data.get("original_effect_id"))
            return {"status":sink.get("state","unknown") if isinstance(sink,dict) else "unknown","sink_receipt":sink}
        return self._run(ctx,command,payload,"project.read",prepare,effect)

    def archive_export(self,ctx,payload):
        return self._archive(ctx,payload,False)
    def archive_repair(self,ctx,payload):
        return self._archive(ctx,payload,True)

    def backup_create(self,ctx,payload):
        def prepare(data):
            if self.provider is None or not self.provider.backup_available: raise KernelError(capability_unavailable("backup root unavailable"))
            _,store=exact(self.store,data["store_ref"],"store")
            exact(self.store,data["policy_ref"])
            if store["payload"].get("store_id")!=self.store.store_id:
                raise KernelError(invalid_input("backup store differs"))
            return {}
        def effect(op):
            manifest=self.provider.backup(op["operation_id"])
            return {"status":"succeeded" if manifest["all_ok"] else "failed","object_type":"backup_manifest","body":manifest}
        return self._run(ctx,"backup.create",payload,"project.admin",prepare,effect)

    def restore_plan(self,ctx,payload):
        require_scope(self.store,ctx.scope,"project.admin")
        def cb(h):
            data=checked_payload("restore.plan",payload)
            ref,row=exact(self.store,data["revision_or_backup_ref"])
            body={**data,"source_digest":row["digest"],"target_ref":None}
            if data["restore_kind"]=="disaster_recovery":
                if ref.object_type!="backup_manifest" or not row["payload"].get("all_ok"):
                    raise KernelError(invalid_input("restore requires a verified backup"))
                target_info=self.provider.restore_target_info if self.provider is not None else None
                if ctx.scope.mode!="test" or target_info is None:
                    raise KernelError(capability_unavailable("only explicitly configured offline test restoration is available"))
                target=self._publish(h,"restore_target","target-"+target_info["target_id"],
                    {**target_info,"store_id":self.store.store_id,"mode":"test","target_scope":"project"})
                body["target_ref"]=target.to_dict()
            else:
                if ref.object_type not in {"requirement","design","rules"}:
                    raise KernelError(invalid_input("business restore only supports editable design records"))
                target=self._publish(h,"restore_target","business-"+ref.object_id,
                    {"object_type":ref.object_type,"object_id":ref.object_id,"target_scope":"project"})
                body["target_ref"]=target.to_dict()
            oid="restore-"+uuid.uuid4().hex[:16]
            h.outcome.object_refs=(self._publish(h,"restore_plan",oid,body),target)
        return UnitOfWork(self.store,ctx,"restore.plan").execute(cb)

    def _restore_inputs(self,data):
        return authorized_restore_inputs(self.store,data)

    def restore_apply(self,ctx,payload):
        data=checked_payload("restore.apply",payload)
        require_scope(self.store,ctx.scope,"project.admin")
        plan,source=self._restore_inputs(data)
        if plan["restore_kind"]=="business_revision":
            def cb(h):
                plan,source=self._restore_inputs(data)
                old=ObjectRef.from_dict(plan["revision_or_backup_ref"])
                head=self.store.get_head(old.object_type,old.object_id,"draft")
                new=h.records.append_revision(old.object_type,old.object_id,source,old.object_type+".v1",parent_ref=old)
                h.records.publish_head(new,"draft",str(head["head_version"]) if head else None)
                h.audit("restore.business_applied",{"plan_ref":data["restore_plan_ref"],"new_ref":new.to_dict()})
                h.outcome.object_refs=(new,)
            return UnitOfWork(self.store,ctx,"restore.apply").execute(cb)
        def prepare(data):
            plan,source=self._restore_inputs(data)
            target_info=self.provider.restore_target_info if self.provider is not None else None
            if target_info is not None and target_info["restore_mode"]=="controlled_replacement":
                raise KernelError(capability_unavailable("controlled restore requires the offline maintenance entry after closing all writers"))
            if ctx.scope.mode!="test" or target_info is None or not self.provider.backup_available:
                raise KernelError(capability_unavailable("offline test restore is not configured"))
            target=exact(self.store,plan["target_ref"],"restore_target")[1]["payload"]
            if target["target_id"]!=target_info["target_id"]:
                raise KernelError(permission_denied("restore target differs from approved target"))
            return {"backup":source}
        def effect(op):
            return self.provider.restore(op["pinned"]["backup"],op["operation_id"])
        return self._run(ctx,"restore.apply",payload,"project.admin",prepare,effect)

    def reconcile(self,ctx,operation_id):
        require_scope(self.store,ctx.scope,"project.admin")
        body=self._operation(operation_id)
        if body["status"] in {"succeeded","failed"}:
            return body
        if self.provider is None:
            raise KernelError(capability_unavailable("evidence provider unavailable"))
        result=None
        if body["command"].startswith("archive."):
            data=body["payload"]
            result=self.provider.reconcile_archive(self._manifest(data["manifest_ref"]),data["sink_id"])
        elif body["command"]=="restore.apply":
            result=self.provider.reconcile_restore(body["pinned"]["backup"],operation_id)
        elif body["command"]=="backup.create":
            result=self.provider.reconcile_backup(operation_id)
        if result is not None:
            self._settle(ctx,operation_id,result)
        return self._operation(operation_id)
