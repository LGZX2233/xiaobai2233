"""Actual public effects and negative handler wiring, no empty-payload claims."""
import pytest
from project_kernel.contracts.dto import ObjectRef
from project_kernel.contracts import sha256_digest
from project_kernel.data.queries.service import QueryService
from project_kernel.contracts.errors import KernelError
from project_kernel.interfaces.rpc.framing import encode_frame,decode_frame
from p01_store.helpers import make_store
from p02_design.helpers import seed,context
from .auth_helpers import build_test_server

def test_legal_task_request_fails_if_real_handler_is_removed(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        srv=build_test_server(store)
        message={"jsonrpc":"2.0","id":"r","method":"kernel.command","params":{
            "protocol_version":"1.0.0","invocation_context_id":"ctx1","idempotency_key":"legal",
            "selector":{"project_id":"proj-a"},"expected_heads":[],"command":"task.create",
            "payload":{"title":"legal","goal":"wiring","requirement_refs":[],"mode":"test"}}}
        handler=srv.command_handlers.pop("task.create")
        failed=decode_frame(srv.handle_line(encode_frame(message)))
        assert failed["error"]["data"]["code"]=="CAPABILITY_UNAVAILABLE"
        assert store.next_commit_seq()==1
        srv.command_handlers["task.create"]=handler
        result=decode_frame(srv.handle_line(encode_frame(message)))
        ref=ObjectRef.from_dict(result["result"]["receipt"]["object_refs"][0])
        assert store.get_revision(ref)["payload"]["title"]=="legal"
    finally:store.close()

def test_approval_pages_keep_original_revisions_after_new_decisions(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        for name in ("a","b","c"):
            seed(store,"approval",name,{"snapshot_id":name,"snapshot_digest":"a"*64,"status":"pending"})
        query=QueryService(store)
        first=query.approvals_queue(status="pending",limit=1)
        seed(store,"approval","b",{"snapshot_id":"b","snapshot_digest":"a"*64,"status":"approved"})
        second=query.approvals_queue(status="pending",limit=1,page_token=first["next_page_token"])
        assert first["queue"][0]["approval_id"]=="c"
        assert second["queue"][0]["approval_id"]=="b"
        assert second["queue"][0]["status"]=="pending"
        assert second["as_of_seq"]==first["as_of_seq"]
        with pytest.raises(KernelError):
            query.approvals_queue(status="pending",limit=1,page_token=first["next_page_token"],
                as_of_seq=store.next_commit_seq()-1)
    finally:store.close()

def test_all_declared_queries_accept_valid_payloads_on_empty_store(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        srv=build_test_server(store)
        def ref(kind):
            return {"project_id":"proj-a","object_type":kind,"object_id":"none","revision_id":"rev-1"}
        payloads={"project.overview":{},"project.timeline":{},"project.trace":{"root_ref":ref("task"),"direction":"both","max_depth":4},
            "requirements.coverage":{},"attempts.compare":{"task_ref":ref("task")},"approvals.queue":{},
            "environment.report":{"task_ref":ref("task")},"archive.status":{"manifest_ref":ref("archive_manifest")},
            "command.receipt":{"idempotency_key":"missing","receipt_domain":"project"},
            "operation.status":{"operation_id":"missing"},"events.read":{"after":{"commit_seq":"0","event_index":0},"limit":10},
            "dataset.preview":{"policy_ref":ref("dataset_policy"),"purpose_ref":ref("dataset_purpose")}}
        assert set(payloads)==set(srv.initialize_result()["supported_queries"])
        for name,payload in payloads.items():
            response=decode_frame(srv.handle_line(encode_frame({"jsonrpc":"2.0","id":"q","method":"kernel.query","params":{
                "protocol_version":"1.0.0","invocation_context_id":"ctx1","selector":{"project_id":"proj-a"},"query":name,"payload":payload}})))
            if name in {"operation.status","dataset.preview","project.trace","archive.status"}:
                assert response["error"]["data"]["code"]=="REFERENCE_NOT_FOUND",(name,response)
            else:
                assert "result" in response,(name,response)
                assert response["result"]["as_of_seq"]=="0",(name,response)
    finally:store.close()

def test_identity_and_legacy_commands_are_not_advertised_or_stubbed(tmp_path):
    store=make_store(tmp_path,project_id="proj-a")
    try:
        srv=build_test_server(store)
        unavailable={
            "project.provision": {"project_id":"proj-b","display_name":"Beta",
                "canonical_root":"/tmp/beta","host_id":"host-1"},
            "project.reconcile": {"provision_request_id":"pr-existing"},
            "project.bind": {"project_id":"proj-a","host_id":"host-1",
                "binding_kind":"workspace","canonical_key":"workspace-1",
                "expected_binding_version":"1"},
            "legacy.import": {"source_root":"/tmp/legacy","source_store_id":"legacy-1",
                "target_project_id":"proj-a","project_mapping":{},"batch_id":"batch-1"},
        }
        declared=set(srv.initialize_result()["supported_commands"])
        assert declared.isdisjoint(unavailable)
        for index,(name,payload) in enumerate(unavailable.items()):
            response=decode_frame(srv.handle_line(encode_frame({"jsonrpc":"2.0","id":str(index),
                "method":"kernel.command","params":{"protocol_version":"1.0.0",
                "invocation_context_id":"ctx1","idempotency_key":f"k-{index}",
                "selector":{"project_id":"proj-a"},"expected_heads":[],
                "command":name,"payload":payload}})))
            assert response["error"]["data"]["code"]=="UNSUPPORTED_COMMAND",(name,response)
    finally:store.close()

def test_identity_rpc_provision_bind_and_durable_idempotency(tmp_path):
    from project_kernel.bootstrap import InvocationContextRegistry, build_identity_server

    root=tmp_path/"identity-data"
    handle_ids=iter(("identity-a","identity-b","identity-c"))
    contexts=InvocationContextRegistry(handle_factory=lambda:next(handle_ids))
    contexts.mint("operator",{"project.admin"},project_id="project-a")
    contexts.mint("operator",{"project.admin"},project_id="project-b")
    contexts.mint("operator",{"project.admin"},project_id="project-c")
    srv=build_identity_server(root,contexts=contexts)
    def invoke(server,rid,key,name,project,payload):
        return decode_frame(server.handle_line(encode_frame({"jsonrpc":"2.0","id":rid,
            "method":"kernel.command","params":{"protocol_version":"1.0.0",
            "invocation_context_id":{"project-a":"identity-a","project-b":"identity-b",
                                     "project-c":"identity-c"}[project],"idempotency_key":key,
            "selector":{"project_id":project},"expected_heads":[],"command":name,
            "payload":payload}})))
    try:
        assert srv.initialize_result()["supported_commands"]==[
            "project.provision","project.reconcile"]
        assert srv.initialize_result()["supported_queries"]==["command.receipt"]
        payload={"display_name":"Project A","canonical_root":str(tmp_path/"project-a"),
                 "host_id":"host-a","workspace_id":"workspace-a"}
        invalid=invoke(srv,"bad","bad","project.provision","project-a",{"display_name":""})
        assert invalid["error"]["data"]["code"]=="INVALID_INPUT"
        result=invoke(srv,"one","provision-key","project.provision","project-a",payload)
        assert "result" in result,result
        assert result["result"]["receipt"]["receipt_domain"]=="identity"
        assert result["result"]["data"]["state"]=="active"
        assert all(binding["unchanged"] is False
                   for binding in result["result"]["data"]["bindings"])
        provision_count=srv.identity_registry.conn.execute(
            "SELECT COUNT(*) FROM provision_receipt WHERE project_id='project-a'").fetchone()[0]
        receipt=result["result"]["receipt"]
    finally:
        srv.identity_registry.close()

    restarted=build_identity_server(root,contexts=contexts)
    try:
        replay=invoke(restarted,"two","provision-key","project.provision","project-a",payload)
        assert replay["result"]["receipt"]==receipt
        assert replay["result"]["data"]["state"]=="active"
        assert restarted.identity_registry.conn.execute(
            "SELECT COUNT(*) FROM provision_receipt WHERE project_id='project-a'").fetchone()[0]==provision_count
        queried=decode_frame(restarted.handle_line(encode_frame({"jsonrpc":"2.0","id":"receipt-query",
            "method":"kernel.query","params":{"protocol_version":"1.0.0",
            "invocation_context_id":"identity-a","selector":{"project_id":"project-a"},
            "query":"command.receipt","payload":{"idempotency_key":"provision-key",
            "receipt_domain":"identity"}}})))
        assert queried["result"]["data"]==receipt
        as_of_zero=decode_frame(restarted.handle_line(encode_frame({"jsonrpc":"2.0","id":"receipt-old",
            "method":"kernel.query","params":{"protocol_version":"1.0.0","as_of_seq":"0",
            "invocation_context_id":"identity-a","selector":{"project_id":"project-a"},
            "query":"command.receipt","payload":{"idempotency_key":"provision-key",
            "receipt_domain":"identity"}}})))
        assert as_of_zero["result"]["data"] is None
        assert as_of_zero["result"]["as_of_seq"]=="0"
        other_project=decode_frame(restarted.handle_line(encode_frame({"jsonrpc":"2.0","id":"receipt-other",
            "method":"kernel.query","params":{"protocol_version":"1.0.0",
            "invocation_context_id":"identity-b","selector":{"project_id":"project-b"},
            "query":"command.receipt","payload":{"idempotency_key":"provision-key",
            "receipt_domain":"identity"}}})))
        assert other_project["result"]["data"] is None
        reconciled=invoke(restarted,"reconcile","reconcile-key","project.reconcile","project-a",
                          {"provision_request_id":result["result"]["data"]["provision_request_id"]})
        assert reconciled["result"]["data"]["state"]=="active"
        conflict=invoke(restarted,"three","provision-key","project.provision","project-a",
                        {**payload,"display_name":"Changed"})
        assert conflict["error"]["data"]["code"]=="IDEMPOTENCY_CONFLICT"
        cross=invoke(restarted,"five","cross-key","project.reconcile","project-b",
                     {"provision_request_id":result["result"]["data"]["provision_request_id"]})
        assert cross["error"]["data"]["code"]=="PERMISSION_DENIED"
        created=invoke(restarted,"eight","project-c-provision","project.provision","project-c",
                       {"display_name":"Project C","canonical_root":str(tmp_path/"project-c"),
                        "host_id":"host-c"})
        assert created["result"]["data"]["state"]=="active"
    finally:
        restarted.identity_registry.close()
