"""Environment facts from an explicitly configured provider; no installation."""
import uuid
from ..internal.provider_ports import EnvironmentProbe
from ..internal.environment_provider import PythonEnvironmentProbe  # Compatibility import.
from ..contracts import sha256_digest
from ..contracts.errors import KernelError, capability_unavailable, invalid_input
from ..data.store.uow import UnitOfWork
from .security import require_scope
from .design.references import checked_payload, exact, validate_refs

_PROBE_RESULT_FIELDS = frozenset({
    "status", "facts", "runtime_path", "checked_at", "probed_at", "probe_error", "state", "error",
})


class EnvironmentService:
    def __init__(self,store,provider: EnvironmentProbe | None = None):
        self.store=store
        self.provider=provider
    def environment_probe(self,ctx,payload):
        require_scope(self.store,ctx.scope,"attempt.execute")
        prepared={}
        def cb(h):
            data=checked_payload("environment.probe",payload)
            validate_refs(self.store,data)
            exact(self.store,data["task_ref"],"task")
            root=exact(self.store,data["execution_root_ref"],"execution_root")[1]["payload"]
            if root.get("task_ref")!=data["task_ref"]:
                raise KernelError(invalid_input("environment root belongs to another task"))
            if self.provider is None:
                raise KernelError(capability_unavailable("environment provider is not configured"))
            recipes=[exact(self.store,r,"recipe")[1]["payload"] for r in data["recipe_refs"]]
            oid="env-"+uuid.uuid4().hex[:16]
            ref=h.records.append_revision("environment_probe",oid,{**data,"status":"pending","mode":ctx.scope.mode},"environment_probe.v1")
            h.records.publish_head(ref,"current")
            h.outcome.object_refs=(ref,)
            h.outcome.operation_id=oid
            prepared.update(data=data,recipes=recipes)
        uow=UnitOfWork(self.store,ctx,"environment.probe")
        receipt=uow.execute(cb)
        if receipt.status!="accepted" or not uow.did_commit:
            return receipt
        try:
            facts=self.provider.probe(prepared["recipes"])
        except Exception as exc:
            facts={"status":"unknown","probe_error":type(exc).__name__+": "+str(exc),"facts":[]}
        def settle(h):
            oid=receipt.operation_id
            head=self.store.get_head("environment_probe",oid,"current")
            observations={key:value for key,value in facts.items() if key in _PROBE_RESULT_FIELDS}
            body={**prepared["data"],**observations,"mode":ctx.scope.mode,"provider_result":facts}
            ref=h.records.append_revision("environment_probe",oid,body,"environment_probe.v1")
            h.records.publish_head(ref,"current",str(head["head_version"]))
            h.outcome.object_refs=(ref,)
        from ..contracts.dto import CommandContext
        settled=UnitOfWork(self.store,CommandContext(ctx.scope,ctx.command_id,receipt.operation_id+":result",sha256_digest(facts)),"environment.result").execute(settle)
        if settled.status=="rejected":
            raise KernelError(settled.error)
        return receipt
