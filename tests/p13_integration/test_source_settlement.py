"""Persisted provider handles govern settlement through the actual RPC entry."""
import json
from project_kernel.contracts import sha256_digest
from project_kernel.evidence import ArtifactStorage
from project_kernel.interfaces.rpc.framing import encode_frame, decode_frame
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch
from p03_attempt.test_replay_regressions import CountingExecutor
from .auth_helpers import build_test_server
from .test_closed_loop import call, latest


def test_source_ingest_settles_only_matching_handle_and_keeps_terminal_result(tmp_path):
    store=make_store(tmp_path)
    try:
        storage=ArtifactStorage(tmp_path/"artifacts")
        srv=build_test_server(store,executor=CountingExecutor("unknown"),artifact_root=tmp_path/"artifacts",
            source_bindings={"user-1":[("host","session","1")]},
            trusted_provider_principals={"user-1":{"counting"}})
        p=prepare_dispatch(store,tmp_path)
        started=call(srv,"proj-a","attempt.start",{"packet_ref":p["packet"].to_dict(),"strategy_id":"s1",
            "execution_root_ref":p["roots"]["s1"].to_dict()},"start")
        body=store.get_revision(latest(store,"attempt",started["operation_id"]))["payload"]
        def ingest(seq,status,epoch="1"):
            result={"result_kind":"execution_result","attempt_id":body["attempt_id"],
                "provider_id":body["provider_id"],"execution_handle_id":body["execution_handle_id"],
                "epoch":epoch,"result":{"status":status,"evidence_mode":"test"}}
            artifact=storage.publish(storage.stage(json.dumps(result).encode(),"application/json"),"application/json")
            payload={"source_stream":{"host_id":"host","origin_session_id":"session","log_generation":"1"},
                "observed_range":{"first":str(seq),"last":str(seq),"truncated":False},
                "events":[{"source_seq":str(seq),"payload_hash":sha256_digest(result),"schema_version":"1.0.0",
                    "payload_artifact_ref":artifact.to_dict(),"evidence_mode":"test"}]}
            return payload
        def raw(command,payload,key):
            return decode_frame(srv.handle_line(encode_frame({"jsonrpc":"2.0","id":"x","method":"kernel.command",
                "params":{"protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-a"},
                    "command":command,"payload":payload,"idempotency_key":key,"expected_heads":[]}})))
        foreign=raw("source.ingest",ingest(1,"completed","99"),"foreign")
        assert foreign["result"]["receipt"]["status"]=="rejected"
        wrong_provider=build_test_server(store,executor=CountingExecutor("unknown"),artifact_root=tmp_path/"artifacts",
            source_bindings={"user-1":[("host","session","1")]},
            trusted_provider_principals={"user-1":{"another-provider"}})
        denied=decode_frame(wrong_provider.handle_line(encode_frame({"jsonrpc":"2.0","id":"x","method":"kernel.command",
            "params":{"protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-a"},
                "command":"source.ingest","payload":ingest(1,"completed"),"idempotency_key":"wrong-provider","expected_heads":[]}})))
        assert denied["result"]["receipt"]["status"]=="rejected"
        ingested=call(srv,"proj-a","source.ingest",ingest(1,"completed"),"matching")
        payload={"execution_handle_id":body["execution_handle_id"],"source_result_ref":ingested["object_refs"][0]}
        settled=call(srv,"proj-a","attempt.settle",payload,"settle")
        assert call(srv,"proj-a","attempt.settle",payload,"settle")==settled
        final=store.get_revision(latest(store,"attempt",body["attempt_id"]))["payload"]
        assert final["status"]=="completed" and final["task_ref"]==p["task"].to_dict()
        late=call(srv,"proj-a","source.ingest",ingest(2,"failed"),"late")
        refused=raw("attempt.settle",{"execution_handle_id":body["execution_handle_id"],
            "source_result_ref":late["object_refs"][0]},"late-settle")
        assert refused["result"]["receipt"]["status"]=="rejected"
        assert store.get_revision(latest(store,"attempt",body["attempt_id"]))["payload"]["status"]=="completed"
    finally:store.close()
