"""Persist execution intent before provider calls; never replay unknown effects.

Strategy write directories remain disjoint from other task/strategy attempts,
including completed attempts. Pending or unknown attempts reserve their physical
directory even when a later execution_root revision uses another object ID.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import uuid
from typing import Any, Iterable, Mapping
from ...contracts import sha256_digest
from ...contracts.dto import CommandContext, ObjectRef, ExecutionHandle
from ...contracts.errors import KernelError, invalid_input, capability_unavailable, stale_revision
from ...data.store.uow import UnitOfWork
from ...data.queries.service import QueryService
from ...domain import flow
from ..security import require_scope
from ..design.references import checked_payload, exact, current

_RESULT_FIELDS = frozenset({
    "status", "evidence_mode", "exit_code", "outputs", "changed_artifacts", "error_refs",
    "test_results", "usage", "usage_unknown_reason", "duration_ms", "source_refs",
    "completeness", "error", "output_artifacts", "cancel_status", "unrecognized_status",
})


def _result_fields(result):
    """Keep provider observations separate from kernel-owned execution identity."""
    return {key: value for key, value in result.items() if key in _RESULT_FIELDS}


class AttemptService:
    def __init__(self, store, executor=None, *, artifact_storage=None, trusted_result_principals=(),
                 trusted_provider_principals: Mapping[str, Iterable[str]] | None = None):
        self.store=store
        self.executor=executor
        self.artifact_storage=artifact_storage
        self.trusted_result_principals=frozenset(trusted_result_principals)
        self.trusted_provider_principals={key:frozenset(value) for key,value in
            (trusted_provider_principals or {}).items()}

    def _head(self, attempt_id):
        head=self.store.get_head("attempt",attempt_id,"current")
        if head is None:
            return None,None
        return self.store.get_revision(ObjectRef(self.store.project_id,"attempt",attempt_id,head["revision_id"]))["payload"],head

    def _attempt_status(self, attempt_id):
        body,_=self._head(attempt_id)
        return body.get("status") if body else None

    def _publish(self,h,kind,oid,body):
        head=self.store.get_head(kind,oid,"current")
        ref=h.records.append_revision(kind,oid,body,kind+".v1")
        h.records.publish_head(ref,"current",str(head["head_version"]) if head else None)
        return ref

    def _derived(self,ctx,key,payload):
        return CommandContext(ctx.scope,ctx.command_id,key,sha256_digest(payload))

    def attempt_start(self,ctx,payload):
        require_scope(self.store,ctx.scope,"attempt.execute")
        prepared={}
        def cb(h):
            data=checked_payload("attempt.start",payload)
            packet_ref,rev=current(self.store,data["packet_ref"],"execution_packet")
            packet=rev["payload"]
            if packet.get("revoked") or packet["mode"]!=ctx.scope.mode:
                raise KernelError(invalid_input("packet revoked or mode differs"))
            if data["strategy_id"] not in {s["strategy_id"] for s in packet["strategies"]}:
                raise KernelError(invalid_input("strategy is outside packet"))
            root_ref,root_rev=exact(self.store,data["execution_root_ref"],"execution_root")
            root=root_rev["payload"]
            _,base_rev=exact(self.store,packet["scope"]["execution_root_ref"],"execution_root")
            path=Path(root.get("path","")).resolve()
            base=Path(base_rev["payload"].get("path","")).resolve()
            if (root.get("task_ref")!=packet["task_ref"] or root.get("strategy_id")!=data["strategy_id"]
                or root.get("parent_ref")!=packet["scope"]["execution_root_ref"]
                or path==base or not path.is_relative_to(base) or not path.is_dir()):
                raise KernelError(invalid_input("execution root is not isolated for this task and strategy"))
            if self.executor is None or self.artifact_storage is None:
                raise KernelError(capability_unavailable("Executor and artifact storage must be configured"))
            caps=self.executor.capabilities()
            levels={"none":0,"directory_only":1,"partial":2,"os_enforced":3}
            if levels.get(caps.supported_sandbox_level,-1)<levels[packet["scope"]["required_sandbox_level"]]:
                raise KernelError(capability_unavailable("provider cannot enforce requested sandbox"))
            if not hasattr(self.executor,"start") and ctx.scope.mode!="test":
                raise KernelError(capability_unavailable("production requires the ExecutorPort interface"))
            for other in QueryService(self.store).latest_revisions("attempt"):
                p=other["payload"]
                previous_root=p.get("execution_root_ref")
                if previous_root is None:
                    continue
                previous=exact(self.store,previous_root,"execution_root")[1]["payload"]
                previous_path=Path(previous["path"]).resolve()
                overlapping=(path==previous_path or path.is_relative_to(previous_path)
                             or previous_path.is_relative_to(path))
                previous_task=p.get("task_ref",{})
                same_task=all(previous_task.get(key)==packet["task_ref"][key]
                              for key in ("project_id","object_type","object_id"))
                same_strategy=(same_task and p.get("strategy_id")==data["strategy_id"])
                if overlapping and not same_strategy:
                    raise KernelError(invalid_input("execution directory overlaps another task or strategy"))
                if overlapping and not flow.attempt_is_terminal(p.get("status")):
                    raise KernelError(invalid_input("execution directory is already active or unknown"))
            task_id=packet["task_ref"]["object_id"]
            task_head=self.store.get_head("task",task_id,"current")
            task=self.store.get_revision(ObjectRef(self.store.project_id,"task",task_id,task_head["revision_id"]))["payload"]
            transition=flow.task_transition(task["phase"],"attempt.start")
            if isinstance(transition,flow.Rejection):
                raise KernelError(transition.error)
            aid="attempt-"+uuid.uuid4().hex[:16]
            body={"attempt_id":aid,"task_ref":packet["task_ref"],"packet_ref":packet_ref.to_dict(),
                  "strategy_id":data["strategy_id"],"execution_root_ref":root_ref.to_dict(),
                  "status":"starting","mode":ctx.scope.mode,"epoch":"1","provider_id":caps.provider_id,
                  "provider_capabilities":caps.to_dict(),"usage":None,"usage_unknown_reason":"provider has not reported usage"}
            r=self._publish(h,"attempt",aid,body)
            self._publish(h,"task",task_id,{**task,"phase":transition.to_state})
            h.outcome.object_refs=(r,)
            h.outcome.operation_id=aid
            prepared.update(body=body,path=str(path),packet_ref=packet_ref,root_ref=root_ref)
        uow=UnitOfWork(self.store,ctx,"attempt.start")
        receipt=uow.execute(cb)
        if receipt.status!="accepted" or not uow.did_commit:
            return receipt
        aid=receipt.operation_id
        body=prepared["body"]
        if hasattr(self.executor,"start"):
            try:
                handle=self.executor.start(prepared["packet_ref"],dict(body),prepared["root_ref"],ctx.scope,"1")
                if (handle.attempt_id!=aid or handle.operation_id!=aid or handle.epoch!="1"
                    or handle.provider_id!=body["provider_id"]):
                    raise ValueError("provider handle ownership mismatch")
            except Exception as exc:
                self._settle(ctx,aid,"unknown",{"status":"unknown","error":{"type":type(exc).__name__,"message":str(exc)}})
                return receipt
            self._record_handle(ctx,aid,handle)
            try:
                outcome=self.executor.poll(ctx.scope,handle)
                if outcome.handle!=handle or outcome.evidence_mode!=ctx.scope.mode:
                    raise ValueError("provider result handle or evidence mode differs")
                result=outcome.to_dict()
            except Exception as exc:
                result={"status":"unknown","error":{"type":type(exc).__name__,"message":str(exc)}}
        else:
            handle=ExecutionHandle("handle-"+aid,body["provider_id"],aid,aid,aid,"1",datetime.now(timezone.utc).isoformat())
            self._record_handle(ctx,aid,handle)
            try:
                result=self.executor.run(body["strategy_id"],prepared["path"])
            except Exception as exc:
                result={"status":"unknown","error":{"type":type(exc).__name__,"message":str(exc)}}
        self._settle(ctx,aid,result.get("status","unknown"),result)
        return receipt

    def _record_handle(self,ctx,aid,handle):
        def cb(h):
            prior,_=self._head(aid)
            h.outcome.object_refs=(self._publish(h,"attempt",aid,{**prior,"status":"running",
                "execution_handle_id":handle.execution_handle_id,"execution_handle":asdict(handle)}),)
        result=UnitOfWork(self.store,self._derived(ctx,aid+":handle",asdict(handle)),"attempt.handle").execute(cb)
        if result.status=="rejected":
            raise KernelError(result.error)

    def _settle(self,ctx,attempt_id,status,result):
        result=dict(result)
        if status not in {"running","completed","failed","cancelled","interrupted","unknown"}:
            result["unrecognized_status"]=status
            status="unknown"
        artifacts={}
        for name in ("stdout","stderr"):
            value=result.pop(name,None)
            if value is not None:
                raw=value.encode("utf-8") if isinstance(value,str) else bytes(value)
                staged=self.artifact_storage.stage(raw,"text/plain")
                artifacts[name]=self.artifact_storage.publish(staged,"text/plain").to_dict()
        result.pop("execution_handle_id",None)
        if artifacts:
            result["output_artifacts"]=artifacts
        result["status"]=status
        receipt=self._apply_attempt_status(ctx,attempt_id,status,attempt_id+":result:"+sha256_digest(result)[:16],result)
        if receipt.status=="rejected":
            raise KernelError(receipt.error)
        return receipt

    def _apply_attempt_status(self,ctx,attempt_id,status,idem_key,result):
        require_scope(self.store,ctx.scope,"attempt.execute")
        def cb(h):
            prior,_=self._head(attempt_id)
            if prior is None:
                raise KernelError(invalid_input("attempt missing"))
            if flow.attempt_is_terminal(prior["status"]):
                h.audit("attempt.late_result",{"attempt_id":attempt_id,"result":result})
                return
            if status!=prior["status"] and not flow.attempt_transition(prior["status"],status):
                raise KernelError(invalid_input("illegal attempt outcome transition"))
            source={"attempt_id":attempt_id,"epoch":prior["epoch"],"provider_id":prior["provider_id"],
                    "execution_handle_id":prior.get("execution_handle_id"),"result":result}
            sr=h.records.append_revision("source_result","result-"+uuid.uuid4().hex[:16],source,"source_result.v1")
            body={**prior,**_result_fields(result),"status":status,"source_result_ref":sr.to_dict()}
            if status=="cancelled":
                body["cancel_status"]="confirmed"
            ref=self._publish(h,"attempt",attempt_id,body)
            h.outcome.object_refs=(ref,)
        return UnitOfWork(self.store,self._derived(ctx,idem_key,result),"attempt.settle").execute(cb)

    def attempt_cancel(self,ctx,payload):
        require_scope(self.store,ctx.scope,"attempt.execute")
        saved={}
        def cb(h):
            data=checked_payload("attempt.cancel",payload)
            ref,_=exact(self.store,data["attempt_ref"],"attempt")
            prior,head=self._head(ref.object_id)
            if flow.attempt_is_terminal(prior["status"]):
                raise KernelError(invalid_input("attempt is already terminal"))
            body={**prior,"cancel_status":"pending","cancel_reason":data["reason"]}
            r=self._publish(h,"attempt",ref.object_id,body)
            h.outcome.object_refs=(r,)
            saved.update(body=body,aid=ref.object_id)
        uow=UnitOfWork(self.store,ctx,"attempt.cancel")
        receipt=uow.execute(cb)
        if receipt.status=="rejected" or not uow.did_commit:
            return receipt
        body=saved["body"]
        if self.executor is not None and self.executor.capabilities().can_cancel and body.get("execution_handle"):
            try:
                handle=ExecutionHandle(**body["execution_handle"])
                outcome=self.executor.cancel(ctx.scope,handle,body["cancel_reason"])
                if outcome.handle!=handle or outcome.evidence_mode!=ctx.scope.mode:
                    raise ValueError("cancel result handle or evidence mode differs")
                self._settle(ctx,saved["aid"],outcome.status,outcome.to_dict())
            except Exception as exc:
                self._settle(ctx,saved["aid"],"unknown",{"status":"unknown","cancel_status":"pending",
                    "error":{"type":type(exc).__name__,"message":str(exc)}})
        return receipt

    def attempt_settle(self,ctx,payload):
        require_scope(self.store,ctx.scope,"attempt.execute")
        def cb(h):
            data=checked_payload("attempt.settle",payload)
            _,row=exact(self.store,data["source_result_ref"],"source_result")
            if row["principal_id"] not in self.trusted_result_principals:
                raise KernelError(invalid_input("result is not from an explicitly trusted ingestion principal"))
            source=row["payload"]
            body,head=self._head(source["attempt_id"])
            if body is None:
                raise KernelError(invalid_input("source result attempt is missing"))
            if body.get("mode")!=ctx.scope.mode:
                raise KernelError(invalid_input("settlement scope differs from the persisted attempt mode"))
            if (data["execution_handle_id"]!=body.get("execution_handle_id")
                or source.get("execution_handle_id")!=body.get("execution_handle_id")
                or source.get("epoch")!=body["epoch"] or source.get("provider_id")!=body["provider_id"]):
                raise KernelError(stale_revision("late or foreign result cannot settle this attempt"))
            if body["provider_id"] not in self.trusted_provider_principals.get(row["principal_id"],()):
                raise KernelError(invalid_input("result principal is not trusted for this provider"))
            result=source["result"]
            if not isinstance(result,dict) or result.get("status") not in {"completed","failed","cancelled","interrupted","unknown","running"}:
                raise KernelError(invalid_input("source result has no valid outcome"))
            if result.get("evidence_mode")!=body["mode"]:
                raise KernelError(invalid_input("source result evidence mode differs"))
            from ..design.references import validate_refs
            validate_refs(self.store,result)
            if not flow.attempt_transition(body["status"],result["status"]):
                raise KernelError(invalid_input("result cannot change terminal state"))
            h.outcome.object_refs=(self._publish(h,"attempt",source["attempt_id"],
                {**body,**_result_fields(result),"source_result_ref":data["source_result_ref"]}),)
        return UnitOfWork(self.store,ctx,"attempt.settle").execute(cb)
