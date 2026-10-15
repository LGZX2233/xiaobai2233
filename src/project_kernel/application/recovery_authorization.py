"""Authorize immutable restore inputs without creating or running a provider."""
from ..contracts.errors import KernelError, permission_denied, artifact_digest_mismatch
from .design.references import current, exact


def authorized_restore_inputs(store, data):
    plan_ref,plan_row=current(store,data["restore_plan_ref"],"restore_plan")
    decision_ref,decision_row=current(store,data["human_decision_ref"],"decision")
    d=decision_row["payload"]
    plan=plan_row["payload"]
    if (decision_row["payload_schema"]!="p04.decision.v1" or not d.get("is_human")
        or d.get("subject_kind")!="restore_plan" or d.get("action")!="restore.apply"
        or d.get("decision")!="approved" or d.get("subject_ref")!=plan_ref.to_dict()
        or d.get("subject_digest")!=plan_row["digest"] or d.get("target_ref")!=plan["target_ref"]
        or d.get("target_scope")!="project"):
        raise KernelError(permission_denied("human decision does not authorize this restore"))
    _,source=exact(store,plan["revision_or_backup_ref"])
    if source["digest"]!=plan["source_digest"]:
        raise KernelError(artifact_digest_mismatch("restore source changed"))
    return plan,source["payload"]


def authorize_restore(store, payload):
    """Return the pinned plan, backup and approved target from a read-only store."""
    plan, source = authorized_restore_inputs(store, payload)
    target = exact(store, plan["target_ref"], "restore_target")[1]["payload"]
    return plan, source, target
