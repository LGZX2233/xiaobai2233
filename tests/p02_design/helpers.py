"""Test-only provider configuration; business baselines use real public services."""
from pathlib import Path
from project_kernel.application.design.service import DesignService
from project_kernel.contracts import ALL_CAPABILITIES, sha256_digest
from project_kernel.contracts.dto import CommandContext, ResolvedScope, ObjectRef
from project_kernel.data.store.uow import UnitOfWork

def context(store, key, payload=None):
    return CommandContext(ResolvedScope(store.project_id, store.store_id, "user-1",
        ALL_CAPABILITIES, "test"), "cmd", key, sha256_digest(payload or {"key":key}))

def seed(store, kind, oid, payload):
    def cb(h):
        head=store.get_head(kind,oid,"current")
        ref=h.records.append_revision(kind,oid,payload,kind+".v1")
        h.records.publish_head(ref,"current",str(head["head_version"]) if head else None)
        h.outcome.object_refs=(ref,)
    result=UnitOfWork(store,context(store,"seed-"+kind+"-"+oid+"-"+sha256_digest(payload)[:12]),"system.ingest").execute(cb)
    assert result.status=="committed",result.error
    return result.object_refs[0]

def prepare_dispatch(store, root_path, strategies=("s1",), prefix="", confirm=True, invoke=None, environment_ref=None):
    svc=DesignService(store)
    def run(name,payload):
        if invoke is not None:
            command={"create_task":"task.create","requirement_save":"requirement.save","requirement_confirm":"requirement.confirm",
                "design_save":"design.save","design_confirm":"design.confirm","rules_save":"rules.save","rules_preview":"rules.preview",
                "rules_publish":"rules.publish","dispatch_draft":"dispatch.draft","dispatch_confirm":"dispatch.confirm"}[name]
            receipt=invoke(command,payload,prefix+name)
            return tuple(ObjectRef.from_dict(ref) for ref in receipt["object_refs"])
        result=getattr(svc,name)(context(store,prefix+name,payload),payload)
        assert result.status=="committed",(name,result.error)
        return result.object_refs
    task=run("create_task",{"title":"isolated task","goal":"verify workflow","requirement_refs":[],"mode":"test"})[0]
    budget=seed(store,"budget",prefix+"budget",{"max_attempts":20})
    network=seed(store,"network_policy",prefix+"network",{"network":"fixture-only"})
    root=seed(store,"execution_root",prefix+"root",{"path":str(Path(root_path).resolve()),"task_ref":task.to_dict()})
    recipe=seed(store,"recipe",prefix+"recipe-i1",{"kind":"automated_test"})
    req_draft=run("requirement_save",{"object_id":prefix+"req-1","title":"output","source_text":"produce output","assumptions":[],"negative_requirements":[],"source_refs":[]})[0]
    item={"item_id":"i1","requirement_ref":req_draft.to_dict(),"recipe_ref":recipe.to_dict(),"required":True,"evidence_type":"automated_test","criterion":"output matches"}
    req,acc=run("requirement_confirm",{"draft_ref":req_draft.to_dict(),"acceptance_items":[item],"confirmed_assumptions":["test isolation"]})
    options=[{"strategy_id":s,"title":s,"hypothesis":"test","risks":[],"acceptance_refs":[acc.to_dict()],"environment_requirements":[],"budget_ref":budget.to_dict()} for s in strategies]
    design=run("design_save",{"object_id":prefix+"d1","requirement_refs":[req.to_dict()],"options":options,"rationale":"compare strategies","interface_refs":[]})[0]
    decision=seed(store,"design_decision",prefix+"decision",{"design_ref":design.to_dict(),"reason":"test selection"})
    run("design_confirm",{"draft_ref":design.to_dict(),"decision_ref":decision.to_dict()})
    rules=run("rules_save",{"ruleset_id":prefix+"ru-1","data_rules":[],"reason":"explicit test policy"})[0]
    preview=run("rules_preview",{"draft_ref":rules.to_dict(),"source_as_of":str(store.next_commit_seq()-1)})[0]
    run("rules_publish",{"draft_ref":rules.to_dict(),"impact_preview_ref":preview.to_dict()})
    if invoke is not None:
        probe_recipe=seed(store,"recipe",prefix+"probe",{"dependencies":[{"name":"python","version_spec":">=3.10"},{"name":"pytest","version_spec":">=1"}]})
        receipt=invoke("environment.probe",{"task_ref":task.to_dict(),"execution_root_ref":root.to_dict(),
            "requirement_refs":[req.to_dict()],"recipe_refs":[probe_recipe.to_dict()]},prefix+"probe")
        oid=receipt["operation_id"]
        head=store.get_head("environment_probe",oid,"current")
        environment=ObjectRef(store.project_id,"environment_probe",oid,head["revision_id"])
    else:
        environment=seed(store,"environment",prefix+"e1",{"status":"ready","task_ref":task.to_dict(),"mode":"test","facts":[]})
    scope={"execution_root_ref":root.to_dict(),"read_paths":[str(root_path)],"write_paths":[str(root_path)],"network_policy_ref":network.to_dict(),"required_sandbox_level":"directory_only"}
    body={"task_ref":task.to_dict(),"design_ref":design.to_dict(),"strategies":options,"scope":scope,"requirement_refs":[req.to_dict()],"acceptance_refs":[acc.to_dict()],"rule_refs":[rules.to_dict()],"environment_ref":environment.to_dict(),"dependency_refs":[],"budget_ref":budget.to_dict(),"base_content_digest":"a"*64,"mode":"test"}
    packet=run("dispatch_draft",body)[0]
    if confirm:
        run("dispatch_confirm",{"draft_ref":packet.to_dict(),"expected_baseline_digest":sha256_digest(body)})
    roots={}
    for strategy in strategies:
        path=Path(root_path)/strategy
        path.mkdir(parents=True,exist_ok=True)
        roots[strategy]=seed(store,"execution_root",prefix+"root-"+strategy,{"path":str(path.resolve()),"task_ref":task.to_dict(),"strategy_id":strategy,"parent_ref":root.to_dict()})
    return dict(task=task,packet=packet,roots=roots,requirement=req,acceptance=acc,design=design,rules=rules,environment=environment,scope=scope,item=item,body=body)
