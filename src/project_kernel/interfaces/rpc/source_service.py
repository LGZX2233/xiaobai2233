"""Only configured host streams may ingest durable, digest-verified source events."""
import json
from ...contracts import sha256_digest
from ...contracts.dto import ArtifactRef, CommandContext
from ...contracts.errors import KernelError, permission_denied, invalid_input, artifact_digest_mismatch
from ...data.store.uow import UnitOfWork
from ...application.security import require_scope
from ...application.design.references import exact

class SourceIngestService:
    def __init__(self,store,*,scope_resolver,bindings,artifact_storage,
                 trusted_provider_principals=None):
        self.store=store
        self.scope_resolver=scope_resolver
        self.bindings={key:frozenset(value) for key,value in bindings.items()}
        self.storage=artifact_storage
        self.trusted_provider_principals={key:frozenset(value) for key,value in
            (trusted_provider_principals or {}).items()}
    def __call__(self,request):
        scope=self.scope_resolver(request)
        require_scope(self.store,scope,"system.ingest")
        stream=(request.stream.host_id,request.stream.origin_session_id,request.stream.log_generation)
        if scope.principal_id!=request.principal_id or stream not in self.bindings.get(scope.principal_id,()):
            raise KernelError(permission_denied("principal is not bound to this host stream"))
        events=[]
        for event in request.events:
            if event.evidence_mode!=scope.mode:
                raise KernelError(invalid_input("source evidence mode differs from scope"))
            ref=ArtifactRef(**event.payload_artifact_ref)
            raw=self.storage.open_read(ref)
            try:
                body=json.loads(raw)
            except (ValueError,UnicodeDecodeError) as exc:
                raise KernelError(invalid_input("source artifact must contain JSON")) from exc
            if sha256_digest(body)!=event.payload_hash:
                raise KernelError(artifact_digest_mismatch("source payload digest differs"))
            events.append({"host_id":stream[0],"origin_session_id":stream[1],"log_generation":stream[2],
                "source_seq":event.source_seq,"schema_version":event.schema_version,
                "body":body,"evidence_mode":event.evidence_mode,"completeness":"complete"})
        ctx=CommandContext(scope,"source-ingest",request.idempotency_key,request.input_hash)
        def cb(h):
            result=h.source.ingest(request.stream_key,events)
            refs=[]
            for event in events:
                body=event["body"]
                if event["source_seq"] not in result["accepted"] or not isinstance(body,dict) or body.get("result_kind")!="execution_result":
                    continue
                required={"attempt_id","epoch","provider_id","execution_handle_id","result"}
                if not required<=body.keys():
                    raise KernelError(invalid_input("execution source result is incomplete"))
                head=self.store.get_head("attempt",body["attempt_id"],"current")
                if head is None:
                    raise KernelError(invalid_input("source result attempt is missing"))
                from ...contracts.dto import ObjectRef
                attempt=self.store.get_revision(ObjectRef(self.store.project_id,"attempt",body["attempt_id"],head["revision_id"]))["payload"]
                if body["provider_id"] not in self.trusted_provider_principals.get(scope.principal_id,()):
                    raise KernelError(permission_denied("principal is not trusted for this provider"))
                if (attempt.get("execution_handle_id")!=body["execution_handle_id"]
                    or attempt["provider_id"]!=body["provider_id"] or attempt["epoch"]!=body["epoch"]):
                    raise KernelError(invalid_input("source result does not match the persisted provider handle"))
                if attempt.get("mode")!=event["evidence_mode"]:
                    raise KernelError(invalid_input("source event differs from the persisted attempt mode"))
                result_body=body["result"]
                if not isinstance(result_body,dict) or result_body.get("evidence_mode")!=attempt["mode"]:
                    raise KernelError(invalid_input("execution result evidence mode is missing or differs from the attempt"))
                oid="source-"+sha256_digest({"stream":request.stream_key,"seq":event["source_seq"]})[:24]
                refs.append(h.records.append_revision("source_result",oid,body,"source_result.v1"))
            h.outcome.object_refs=tuple(refs)
            h.audit("source.ingested",{"stream":request.stream_key,**result,
                "observed_range":request.observed_range.to_dict(),
                "event_metadata":[event.to_dict() for event in request.events]})
        return UnitOfWork(self.store,ctx,"source.ingest").execute(cb)
