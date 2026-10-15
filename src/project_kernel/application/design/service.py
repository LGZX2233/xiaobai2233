"""Immutable requirements, complete execution packets and bounded data rules."""
from __future__ import annotations
from copy import deepcopy
import uuid
from typing import Any
from ...contracts import sha256_digest
from ...contracts.dto import CommandContext, CommandReceipt, ObjectRef, Condition
from ...contracts.errors import KernelError, invalid_input, required_fact_unknown, stale_revision, snapshot_changed, permission_denied
from ...data.store.store import Store
from ...data.queries.service import QueryService
from ...data.store.uow import UnitOfWork
from ...domain import flow
from ...domain.design.rules import DataRule, evaluate_rules
from ..security import require_scope
from .references import checked_payload, exact, current, validate_refs

def _new_id(kind):
    return f"{kind}-{uuid.uuid4().hex[:12]}"

_RULE_PATHS = frozenset({"task.phase", "task.mode", "packet.mode", "mode",
                         "scope.required_sandbox_level", "environment.status",
                         "provider.supported_sandbox_level", "provider.can_cancel"})

def _condition(raw):
    if "all" in raw:
        return Condition(all=tuple(_condition(x) for x in raw["all"]))
    if "any" in raw:
        return Condition(any=tuple(_condition(x) for x in raw["any"]))
    if "not" in raw:
        return Condition(not_=_condition(raw["not"]))
    if raw.get("path") not in _RULE_PATHS:
        raise KernelError(invalid_input("fact path is not declared by the kernel"))
    return Condition(path=raw["path"], operator=raw["operator"], value=raw["value"])

def _rules(raws):
    return [DataRule(r["rule_id"], r["enabled"], _condition(r["when"]),
                     r["effect"], r["reason"]) for r in raws]

class DesignService:
    def __init__(self, store: Store):
        self.store = store

    def _run(self, ctx, command, payload, callback, capability="design.write"):
        require_scope(self.store, ctx.scope, capability)
        def cb(h):
            body = checked_payload(command, payload)
            callback(h, body)
        return UnitOfWork(self.store, ctx, command).execute(cb)

    def _expected(self, ctx, object_id, pointer, object_type=None):
        for eh in ctx.expected_heads:
            if (eh.object_ref.object_id == object_id and eh.pointer_name == pointer
                    and (object_type is None or eh.object_ref.object_type == object_type)):
                return eh.expected_head_version
        return None

    def _publish(self, h, ref, pointer="current"):
        head = self.store.get_head(ref.object_type, ref.object_id, pointer)
        h.records.publish_head(ref, pointer, expected_head_version=str(head["head_version"]) if head else None)

    def create_task(self, ctx, payload):
        def cb(h, body):
            validate_refs(self.store, body)
            if body["mode"] != ctx.scope.mode:
                raise KernelError(permission_denied("task mode differs from trusted scope"))
            oid = _new_id("task")
            r = h.records.append_revision("task", oid, {**body, "task_id": oid, "phase": "draft"}, "task.v1")
            h.records.publish_head(r, "current")
            h.outcome.object_refs = (r,)
        return self._run(ctx, "task.create", payload, cb)

    def requirement_save(self, ctx, payload):
        def cb(h, body):
            validate_refs(self.store, body)
            oid = body.pop("object_id", None) or _new_id("requirement")
            parent = ObjectRef.from_dict(body.pop("parent_ref")) if "parent_ref" in body else None
            if parent and (parent.object_type != "requirement" or parent.object_id != oid):
                raise KernelError(invalid_input("parent is not this requirement"))
            r = h.records.append_revision("requirement", oid, body, "requirement.v1", parent_ref=parent)
            h.records.publish_head(r, "draft", self._expected(ctx, oid, "draft", "requirement"))
            h.outcome.object_refs = (r,)
        return self._run(ctx, "requirement.save", payload, cb)

    def requirement_confirm(self, ctx, payload):
        def cb(h, body):
            ref, draft = current(self.store, body["draft_ref"], "requirement", "draft")
            items = body["acceptance_items"]
            if not any(i["required"] for i in items):
                raise KernelError(required_fact_unknown("zero required acceptance items"))
            if len({i["item_id"] for i in items}) != len(items):
                raise KernelError(invalid_input("duplicate acceptance item IDs"))
            for item in items:
                if item["requirement_ref"] != ref.to_dict():
                    raise KernelError(invalid_input("acceptance must bind the exact requirement draft"))
                exact(self.store, item["recipe_ref"], "recipe")
            acceptance = h.records.append_revision("acceptance", ref.object_id,
                {"requirement_ref": ref.to_dict(), "acceptance_items": items}, "acceptance.v1")
            self._publish(h, acceptance)
            confirmed = h.records.append_revision("requirement", ref.object_id,
                {**draft["payload"], "confirmed_assumptions": body["confirmed_assumptions"],
                 "acceptance_items": items, "acceptance_refs": [acceptance.to_dict()],
                 "confirmed_from_ref": ref.to_dict()}, "requirement.v1", parent_ref=ref)
            h.records.publish_head(confirmed, "current", self._expected(ctx, ref.object_id, "current", "requirement"))
            h.outcome.object_refs = (confirmed, acceptance)
        return self._run(ctx, "requirement.confirm", payload, cb)

    def design_save(self, ctx, payload):
        def cb(h, body):
            validate_refs(self.store, body)
            oid = body.pop("object_id", None) or _new_id("design")
            parent = ObjectRef.from_dict(body.pop("parent_ref")) if "parent_ref" in body else None
            options = [x["strategy_id"] for x in body["options"]]
            if len(set(options)) != len(options) or body.get("selected_strategy_id", options[0]) not in options:
                raise KernelError(invalid_input("invalid or duplicate selected strategy"))
            r = h.records.append_revision("design", oid, body, "design.v1", parent_ref=parent)
            h.records.publish_head(r, "draft", self._expected(ctx, oid, "draft", "design"))
            h.outcome.object_refs = (r,)
        return self._run(ctx, "design.save", payload, cb)

    def design_confirm(self, ctx, payload):
        def cb(h, body):
            ref, _ = current(self.store, body["draft_ref"], "design", "draft")
            exact(self.store, body["decision_ref"])
            h.records.publish_head(ref, "current", self._expected(ctx, ref.object_id, "current", "design"))
            h.audit("design.confirmed", {"design_ref": ref.to_dict(), "decision_ref": body["decision_ref"]})
            h.outcome.object_refs = (ref,)
        return self._run(ctx, "design.confirm", payload, cb)

    def dispatch_draft(self, ctx, payload):
        def cb(h, body):
            validate_refs(self.store, body)
            exact(self.store, body["task_ref"], "task")
            current(self.store, body["design_ref"], "design")
            for ref in body["requirement_refs"]:
                current(self.store, ref, "requirement")
            for ref in body["acceptance_refs"]:
                current(self.store, ref, "acceptance")
            for ref in body["rule_refs"]:
                current(self.store, ref, "rules")
            if body["mode"] != ctx.scope.mode:
                raise KernelError(permission_denied("packet mode differs from trusted scope"))
            ids = [s["strategy_id"] for s in body["strategies"]]
            if len(ids) != len(set(ids)):
                raise KernelError(invalid_input("duplicate strategies"))
            declared = {sha256_digest(r) for r in body["acceptance_refs"]}
            for strategy in body["strategies"]:
                if not {sha256_digest(r) for r in strategy["acceptance_refs"]} <= declared:
                    raise KernelError(invalid_input("strategy acceptance is outside packet baseline"))
            r = h.records.append_revision("execution_packet", _new_id("packet"), body, "execution_packet.v1")
            h.records.publish_head(r, "draft")
            h.outcome.object_refs = (r,)
        return self._run(ctx, "dispatch.draft", payload, cb)

    def dispatch_confirm(self, ctx, payload):
        def cb(h, data):
            ref, draft = current(self.store, data["draft_ref"], "execution_packet", "draft")
            body = draft["payload"]
            validate_refs(self.store, body)
            if sha256_digest(body) != data["expected_baseline_digest"]:
                raise KernelError(snapshot_changed())
            for raw in body["requirement_refs"] + body["acceptance_refs"] + body["rule_refs"] + [body["design_ref"]]:
                current(self.store, raw)
            task_ref = ObjectRef.from_dict(body["task_ref"])
            task_head = self.store.get_head("task", task_ref.object_id, "current")
            if task_head is None:
                raise KernelError(required_fact_unknown("task has no current revision"))
            task = exact(self.store, ObjectRef(self.store.project_id, "task", task_ref.object_id, task_head["revision_id"]))[1]["payload"]
            env = exact(self.store, body["environment_ref"])[1]["payload"]
            if env.get("status")!="ready" or env.get("task_ref")!=body["task_ref"]:
                raise KernelError(required_fact_unknown("environment is missing, blocked or belongs to another task"))
            facts = {"task": task, "packet": body, "scope": body["scope"], "environment": env, "mode": ctx.scope.mode}
            rules = []
            for raw in body["rule_refs"]:
                rules.extend(_rules(exact(self.store, raw)[1]["payload"].get("data_rules", [])))
            result = evaluate_rules(rules, facts)
            if not result.passed:
                raise KernelError(required_fact_unknown("rules block dispatch: " + ",".join(result.decisions)))
            transition = flow.task_transition(task["phase"], "dispatch.confirm")
            if isinstance(transition, flow.Rejection):
                raise KernelError(transition.error)
            h.records.publish_head(ref, "current", self._expected(ctx, ref.object_id, "current", "execution_packet"))
            task_new = h.records.append_revision("task", task_ref.object_id,
                {**task, "phase": transition.to_state, "packet_ref": ref.to_dict()}, "task.v1")
            self._publish(h, task_new)
            h.outcome.object_refs = (ref,)
        return self._run(ctx, "dispatch.confirm", payload, cb, "dispatch.confirm")

    def dispatch_revoke(self, ctx, payload):
        def cb(h, body):
            ref, packet = current(self.store, body["packet_ref"], "execution_packet")
            attempts = QueryService(self.store).latest_revisions("attempt")
            for item in attempts:
                p = item["payload"]
                if p.get("packet_ref") == ref.to_dict() and not flow.attempt_is_terminal(p.get("status", "unknown")):
                    raise KernelError(required_fact_unknown("active attempts must be cancelled and settled first"))
            revoked = h.records.append_revision("execution_packet", ref.object_id,
                {**packet["payload"], "revoked": True, "revoke_reason": body["reason"]}, "execution_packet.v1", parent_ref=ref)
            self._publish(h, revoked)
            task_id = packet["payload"]["task_ref"]["object_id"]
            head = self.store.get_head("task", task_id, "current")
            task = exact(self.store, ObjectRef(self.store.project_id, "task", task_id, head["revision_id"]))[1]["payload"]
            transition = flow.task_transition(task["phase"], "dispatch.revoke")
            if isinstance(transition, flow.Rejection):
                raise KernelError(transition.error)
            new = h.records.append_revision("task", task_id, {**task, "phase": transition.to_state}, "task.v1")
            self._publish(h, new)
            h.outcome.object_refs = (revoked,)
        return self._run(ctx, "dispatch.revoke", payload, cb, "dispatch.confirm")

    def rules_save(self, ctx, payload):
        def cb(h, body):
            validate_refs(self.store, body)
            _rules(body["data_rules"])
            ids = [r["rule_id"] for r in body["data_rules"]]
            if len(ids) != len(set(ids)):
                raise KernelError(invalid_input("duplicate rule IDs"))
            oid = body.pop("ruleset_id", None) or _new_id("rules")
            r = h.records.append_revision("rules", oid, body, "rules.v1")
            h.records.publish_head(r, "draft", self._expected(ctx, oid, "draft", "rules"))
            h.outcome.object_refs = (r,)
        return self._run(ctx, "rules.save", payload, cb, "rules.publish")

    def rules_preview(self, ctx, payload):
        def cb(h, body):
            ref, rev = exact(self.store, body["draft_ref"], "rules")
            seq = int(body["source_as_of"])
            if seq > self.store.next_commit_seq() - 1:
                raise KernelError(required_fact_unknown("preview watermark is in the future"))
            rules = _rules(rev["payload"]["data_rules"])
            impacts = []
            for item in QueryService(self.store).latest_revisions("task", as_of_seq=seq):
                result = evaluate_rules(rules, {"task": item["payload"], "mode": ctx.scope.mode})
                impacts.append({"task_id": item["object_id"], "blocked": result.blocked,
                                "require_human": result.require_human, "decisions": list(result.decisions)})
            r = h.records.append_revision("rule_impact_preview", _new_id("preview"),
                {"draft_ref": ref.to_dict(), "draft_digest": rev["digest"],
                 "source_as_of": str(seq), "impacts": impacts}, "rule_impact_preview.v1")
            h.outcome.object_refs = (r,)
        return self._run(ctx, "rules.preview", payload, cb, "rules.publish")

    def rules_publish(self, ctx, payload):
        def cb(h, body):
            ref, rev = current(self.store, body["draft_ref"], "rules", "draft")
            _, preview = exact(self.store, body["impact_preview_ref"], "rule_impact_preview")
            if preview["payload"].get("draft_ref") != ref.to_dict() or preview["payload"].get("draft_digest") != rev["digest"]:
                raise KernelError(stale_revision("impact preview belongs to another draft"))
            h.records.publish_head(ref, "current", self._expected(ctx, ref.object_id, "current", "rules"))
            h.audit("rules.published", {"rules_ref": ref.to_dict(), "preview_ref": body["impact_preview_ref"],
                                         "effective_seq": str(h.records.commit_seq), "existing_packets_unchanged": True})
            h.outcome.object_refs = (ref,)
        return self._run(ctx, "rules.publish", payload, cb, "rules.publish")
