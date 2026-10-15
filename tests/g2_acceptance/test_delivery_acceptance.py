"""G2 AC18-26: isolated, project-bound machine/human RPC acceptance evidence."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from project_kernel.application.environment_service import PythonEnvironmentProbe
from project_kernel.bootstrap import build_server, build_human_server, InvocationContextRegistry
from project_kernel.contracts import ALL_CAPABILITIES, sha256_digest
from project_kernel.contracts.dto import ArtifactRef, CheckResult, CommandContext, ObjectRef, ResolvedScope
from project_kernel.data.store.store import Store
from project_kernel.data.store.uow import UnitOfWork
from project_kernel.evidence import ArtifactStorage, BundleExporter
from project_kernel.evidence.delivery_provider import BundleDeliveryProvider
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.invocation import InteractionProof
from p03_attempt.fixture_executor import FixtureSubprocessExecutor


class Checks:
    """Explicit test provider; reads real candidate bytes and pinned acceptance."""

    def __init__(self, store, storage):
        self.store, self.storage = store, storage
        self.result = "pass"

    def run(self, scope, attempt, candidate, acceptance_refs):
        payload = self.store.get_revision(candidate)["payload"]
        for raw in payload["artifacts"]:
            assert self.storage.open_read(ArtifactRef(**raw)) == b"G2 isolated deliverable\n"
        items = []
        for raw in acceptance_refs:
            ref = raw if isinstance(raw, ObjectRef) else ObjectRef.from_dict(raw)
            items.extend(self.store.get_revision(ref)["payload"]["acceptance_items"])
        return tuple(CheckResult(item["item_id"], ObjectRef.from_dict(item["recipe_ref"]),
            candidate_digest=payload["candidate_digest"], result=self.result, evidence_mode="test")
            for item in items)


class RpcHarness:
    """Host seeds only provider configuration and captured candidate revisions."""

    def __init__(self, root):
        self.root = root
        self.store = Store.open_project(root / "project.sqlite", "proj-a", "store-a")
        self.storage = ArtifactStorage(root / "artifacts")
        self.exporter = BundleExporter(root / "exports", self.storage)
        self.provider = BundleDeliveryProvider(self.exporter)
        self.checks = Checks(self.store, self.storage)
        self.trace, self.seeds, self.observed, self.calls = [], [], {}, []
        self.rebuild()

    def rebuild(self):
        machine = InvocationContextRegistry(handle_factory=lambda: "machine-ctx")
        machine.mint("machine-test", ALL_CAPABILITIES, project_id="proj-a")
        human = InvocationContextRegistry(handle_factory=lambda: "human-ctx")
        human.mint_human("human-test", ALL_CAPABILITIES, project_id="proj-a",
            proof=InteractionProof("round4-isolated-user-action", True))
        self.machine = build_server(self.store, principal="machine-test", contexts=machine, artifact_root=self.root / "artifacts",
            delivery_provider=self.provider, bundle_exporter=None,
            executor=FixtureSubprocessExecutor({"s1": [sys.executable, "-B", "-c", "print('executed')"]}),
            environment_provider=PythonEnvironmentProbe(), check_provider=self.checks,
            evidence_config={"trusted_staging_principals": {"host-test"},
                "exporters": {"exports": self.exporter}}, mode="test")
        self.human = build_human_server(self.store, principal="human-test", contexts=human, mode="test")

    def raw(self, name, body, key="query", *, human=False, query=False, extra=None, server=None, handle=None):
        params = {"protocol_version": "1.0.0", "invocation_context_id": handle or ("human-ctx" if human else "machine-ctx"),
            "selector": {"project_id": "proj-a"}, "payload": body}
        params.update({"query": name} if query else {"command": name, "expected_heads": [], "idempotency_key": key})
        params.update(extra or {})
        request = {"jsonrpc": "2.0", "id": key, "method": "kernel.query" if query else "kernel.command", "params": params}
        response = decode_frame((server or (self.human if human else self.machine)).handle_line(encode_frame(request)))
        self.trace.append({"entry": "build_human_server" if human else "build_server", "request": request, "response": response})
        return response

    def invoke(self, name, body, key, *, human=False, extra=None):
        response = self.raw(name, body, key, human=human, extra=extra)
        assert "error" not in response, response
        receipt = response["result"]["receipt"]
        assert receipt["status"] in {"committed", "accepted"}, receipt
        return receipt

    def query(self, name, body):
        response = self.raw(name, body, query=True)
        assert "error" not in response, response
        return response["result"]["data"]

    def latest(self, kind, oid):
        head = self.store.get_head(kind, oid, "current")
        return ObjectRef("proj-a", kind, oid, head["revision_id"])

    def payload(self, ref):
        return self.store.get_revision(ref)["payload"]

    def seed(self, kind, oid, payload):
        key = "host-seed-" + kind + "-" + sha256_digest(payload)[:24]
        ctx = CommandContext(ResolvedScope("proj-a", "store-a", "host-test", ALL_CAPABILITIES, "test"),
            key, key, sha256_digest(payload))
        def callback(handle):
            head = self.store.get_head(kind, oid, "current")
            ref = handle.records.append_revision(kind, oid, payload, kind + ".v1")
            handle.records.publish_head(ref, "current", str(head["head_version"]) if head else None)
            handle.outcome.object_refs = (ref,)
        receipt = UnitOfWork(self.store, ctx, "system.ingest").execute(callback)
        assert receipt.status == "committed", receipt.error
        ref = receipt.object_refs[0]
        self.seeds.append({"scope": "host-owned configuration/candidate/fault injection", "ref": ref.to_dict(),
            "payload": payload, "digest": self.store.get_revision(ref)["digest"]})
        return ref

    def prepare(self, *, required=True):
        ref = lambda receipt: ObjectRef.from_dict(receipt["object_refs"][0])
        self.task = ref(self.invoke("task.create", {"title": "isolated delivery", "goal": "G2 acceptance",
            "requirement_refs": [], "mode": "test"}, "task"))
        budget = self.seed("budget", "budget", {"max_attempts": 10})
        network = self.seed("network_policy", "network", {"network": "fixture-only"})
        execution = self.seed("execution_root", "root", {"path": str(self.root.resolve()), "task_ref": self.task.to_dict()})
        recipe = self.seed("recipe", "check", {"kind": "automated_test"})
        self.requirement_draft = ref(self.invoke("requirement.save", {"object_id": "req", "title": "output",
            "source_text": "produce isolated output", "assumptions": [], "negative_requirements": [], "source_refs": []}, "req"))
        self.item = {"item_id": "i1", "requirement_ref": self.requirement_draft.to_dict(), "recipe_ref": recipe.to_dict(),
            "required": required, "evidence_type": "automated_test", "criterion": "output matches"}
        confirmed = self.invoke("requirement.confirm", {"draft_ref": self.requirement_draft.to_dict(),
            "acceptance_items": [self.item], "confirmed_assumptions": ["test isolation"]}, "confirm-req")
        self.requirement, self.acceptance = map(ObjectRef.from_dict, confirmed["object_refs"])
        option = {"strategy_id": "s1", "title": "s1", "hypothesis": "fixed fixture", "risks": [],
            "acceptance_refs": [self.acceptance.to_dict()], "environment_requirements": [], "budget_ref": budget.to_dict()}
        design = ref(self.invoke("design.save", {"object_id": "design", "requirement_refs": [self.requirement.to_dict()],
            "options": [option], "rationale": "isolated fixture", "interface_refs": []}, "design"))
        decision = self.seed("design_decision", "design-decision", {"design_ref": design.to_dict(), "reason": "test fixture"})
        self.invoke("design.confirm", {"draft_ref": design.to_dict(), "decision_ref": decision.to_dict()}, "confirm-design")
        self.rules = ref(self.invoke("rules.save", {"ruleset_id": "rules", "data_rules": [], "reason": "test policy"}, "rules"))
        preview = ref(self.invoke("rules.preview", {"draft_ref": self.rules.to_dict(), "source_as_of": str(self.store.next_commit_seq() - 1)}, "preview"))
        self.invoke("rules.publish", {"draft_ref": self.rules.to_dict(), "impact_preview_ref": preview.to_dict()}, "publish-rules")
        probe = self.seed("recipe", "probe", {"dependencies": [{"name": "python", "version_spec": ">=3.10"}]})
        probed = self.invoke("environment.probe", {"task_ref": self.task.to_dict(), "execution_root_ref": execution.to_dict(),
            "requirement_refs": [self.requirement.to_dict()], "recipe_refs": [probe.to_dict()]}, "probe")
        environment = self.latest("environment_probe", probed["operation_id"])
        body = {"task_ref": self.task.to_dict(), "design_ref": design.to_dict(), "strategies": [option],
            "scope": {"execution_root_ref": execution.to_dict(), "read_paths": [str(self.root)], "write_paths": [str(self.root)],
                "network_policy_ref": network.to_dict(), "required_sandbox_level": "directory_only"},
            "requirement_refs": [self.requirement.to_dict()], "acceptance_refs": [self.acceptance.to_dict()],
            "rule_refs": [self.rules.to_dict()], "environment_ref": environment.to_dict(), "dependency_refs": [],
            "budget_ref": budget.to_dict(), "base_content_digest": "a" * 64, "mode": "test"}
        self.packet = ref(self.invoke("dispatch.draft", body, "packet"))
        self.invoke("dispatch.confirm", {"draft_ref": self.packet.to_dict(), "expected_baseline_digest": sha256_digest(body)}, "dispatch")
        strategy_root = self.root / "s1"
        strategy_root.mkdir()
        strategy = self.seed("execution_root", "strategy-root", {"path": str(strategy_root.resolve()), "task_ref": self.task.to_dict(),
            "strategy_id": "s1", "parent_ref": execution.to_dict()})
        attempted = self.invoke("attempt.start", {"packet_ref": self.packet.to_dict(), "strategy_id": "s1", "execution_root_ref": strategy.to_dict()}, "attempt")
        self.attempt = self.latest("attempt", attempted["operation_id"])
        staged = self.storage.stage(b"G2 isolated deliverable\n", "text/plain")
        retention = self.seed("retention_policy", "retention", {"name": "default"})
        staged_ref = self.seed("staging", "captured-file", {"locator": staged.staged_locator, "digest": staged.sha256})
        registered = self.invoke("artifact.register", {"trusted_staged_locator_ref": staged_ref.to_dict(), "digest": staged.sha256,
            "source_ref": self.attempt.to_dict(), "media_type": "text/plain", "retention_policy_ref": retention.to_dict()}, "artifact")
        result = self.operation(registered["operation_id"])
        self.artifact = ArtifactRef(**self.payload(ObjectRef.from_dict(result["result_refs"][0]))["artifact"])
        self.candidate = self.seed("candidate_manifest", "candidate", {"attempt_ref": self.attempt.to_dict(),
            "candidate_digest": staged.sha256, "artifacts": [self.artifact.to_dict()]})
        self.target = self.seed("delivery_target", "target", {"method": "bundle", "sink_id": "exports",
            "exports_root": str((self.root / "exports").resolve())})

    def verify(self, *, candidate=None, acceptance=None, key="verify"):
        receipt = self.invoke("verification.run", {"attempt_ref": self.attempt.to_dict(),
            "candidate_manifest_ref": (candidate or self.candidate).to_dict(),
            "acceptance_refs": [(acceptance or self.acceptance).to_dict()]}, key)
        self.report = ObjectRef.from_dict(receipt["object_refs"][0])
        return self.payload(self.report)

    def ready(self):
        self.prepare()
        assert self.verify()["passed"] is True
        self.selection = self.invoke("attempt.select", {"attempt_ref": self.attempt.to_dict(),
            "comparison_refs": [self.attempt.to_dict()], "purpose": "delivery", "reason": "select verified fixture"}, "select")["object_refs"][0]

    def request(self):
        receipt = self.invoke("delivery.request", self.request_payload(), "request")
        self.approval_ref = ObjectRef.from_dict(receipt["object_refs"][0])
        self.approval = self.payload(self.approval_ref)
        self.snapshot_ref = self.latest("delivery_snapshot", self.approval["snapshot_id"])
        self.snapshot = self.payload(self.snapshot_ref)
        return self.approval

    def request_payload(self):
        return {"selection_ref": self.selection, "candidate_ref": self.candidate.to_dict(), "target_ref": self.target.to_dict()}

    def approve(self):
        return self.invoke("approval.decide", {**self.apply_payload(), "decision": "approved", "reason": "isolated human reviewed current digest"}, "approve", human=True)

    def apply_payload(self):
        return {"approval_id": self.approval["approval_id"], "snapshot_digest": self.approval["snapshot_digest"]}

    def phase(self):
        return self.payload(self.latest("task", self.task.object_id))["phase"]

    def change_requirement(self, source_text):
        head = self.store.get_head("requirement", "req", "draft")
        draft = self.invoke("requirement.save", {"object_id": "req", "title": "output", "source_text": source_text,
            "assumptions": [], "negative_requirements": [], "source_refs": []}, "req-changed",
            extra={"expected_heads": [{"object_ref": self.requirement_draft.to_dict(), "pointer_name": "draft",
                "expected_head_version": str(head["head_version"])}]})["object_refs"][0]
        current = self.store.get_head("requirement", "req", "current")
        return self.invoke("requirement.confirm", {"draft_ref": draft,
            "acceptance_items": [{**self.item, "requirement_ref": draft, "criterion": "changed criterion"}],
            "confirmed_assumptions": []}, "confirm-new", extra={"expected_heads": [{"object_ref": self.requirement.to_dict(),
                "pointer_name": "current", "expected_head_version": str(current["head_version"])}]})

    def operation(self, oid):
        return self.query("operation.status", {"operation_id": oid})

    def save(self):
        artifacts = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and not any(path.name.endswith(ext) for ext in (".sqlite", "-wal", "-shm")) and not path.name.endswith("-evidence.json"):
                artifacts.append({"path": str(path.relative_to(self.root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size})
        data = {"nodeid": self.nodeid, "mode": "test", "host": "independent Python, non-DSH", "sandbox": "directory_only",
            "roots": {"test": str(self.root.resolve()), "database": str((self.root / "project.sqlite").resolve()),
                "artifacts": str((self.root / "artifacts").resolve()), "exports": str((self.root / "exports").resolve())},
            "host_seeds": self.seeds, "rpc": self.trace, "observed": self.observed, "files": artifacts}
        (self.root / "delivery-evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.store.close()


@pytest.fixture
def delivery(tmp_path, request):
    harness = RpcHarness(tmp_path)
    harness.nodeid = request.node.nodeid
    try:
        yield harness
    finally:
        harness.save()


def _code(response):
    if "error" in response:
        return response["error"]["data"]["code"]
    return response["result"]["receipt"].get("error", {}).get("code")


@pytest.mark.parametrize("case", ["zero_required", "skipped", "unknown", "old_candidate", "old_acceptance"])
def test_ac18_public_verification_never_passes_incomplete_or_old_evidence(delivery, case):
    h = delivery
    h.prepare()
    if case == "zero_required":
        h.acceptance = h.seed("acceptance", "optional-only", {"acceptance_items": [{**h.item, "required": False}]})
    if case in {"skipped", "unknown"}:
        h.checks.result = case
    if case == "old_candidate":
        h.seed("candidate_manifest", "candidate", {**h.payload(h.candidate), "candidate_digest": "c" * 64})
    if case == "old_acceptance":
        h.change_requirement("changed output")
    report = h.verify()
    h.observed.update(case=case, report=report, phase=h.phase())
    assert report["passed"] is False
    assert report["result"] in {"incomplete", "failed"}
    assert h.phase() != "delivery_ready"


def test_ac19_public_request_is_explicit_pending_and_never_auto_approves(delivery):
    h = delivery
    h.ready()
    assert h.phase() == "delivery_ready"
    assert h.query("approvals.queue", {})["queue"] == []
    approval = h.request()
    assert approval["status"] == "pending" and approval["operation_id"] is None
    assert h.phase() == "approval_pending"
    assert _code(h.raw("delivery.apply", h.apply_payload(), "premature-apply")) == "APPROVAL_INVALID"
    h.observed.update(approval=approval, phase=h.phase(), approvals=h.query("approvals.queue", {}))


def test_ac20_public_human_proof_and_digest_reject_machine_and_spoofing(delivery):
    h = delivery
    h.ready()
    h.request()
    body = {**h.apply_payload(), "decision": "approved", "reason": "review current digest"}
    assert _code(h.raw("approval.decide", body, "machine-approve")) == "UNSUPPORTED_COMMAND"
    assert _code(h.raw("approval.decide", {**body, "actor": "human", "role": "admin"}, "forged-role", human=True)) == "INVALID_INPUT"
    registry = InvocationContextRegistry(handle_factory=lambda: "unverified-ctx")
    registry.mint("model-claimed-human", ALL_CAPABILITIES, project_id="proj-a")
    unverified = build_human_server(h.store, principal="model-claimed-human", contexts=registry, mode="test")
    assert _code(h.raw("approval.decide", body, "unverified", human=True, server=unverified, handle="unverified-ctx")) == "HUMAN_IDENTITY_UNAVAILABLE"
    assert _code(h.raw("approval.decide", {**body, "snapshot_digest": "b" * 64}, "wrong-digest", human=True)) == "APPROVAL_INVALID"
    h.approve()
    approval = h.payload(h.latest("approval", h.approval["approval_id"]))
    assert approval["status"] == "approved" and approval["decided_by"] == "human-test" and approval["decided_human"] is True
    assert approval["snapshot_digest"] == sha256_digest(h.snapshot["body"])
    h.observed.update(approval=approval, interaction_proof={"source": "round4-isolated-user-action", "verified": True})


@pytest.mark.parametrize("initial", ["pending", "approved"])
def test_ac21_public_requirement_change_supersedes_current_approval(delivery, initial):
    h = delivery
    h.ready()
    h.request()
    approved = h.approve() if initial == "approved" else None
    confirmed = h.change_requirement("materially changed requirement")
    assert h.payload(h.latest("approval", h.approval["approval_id"]))["status"] == "superseded"
    count = h.store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0]
    h.query("approvals.queue", {})
    confirm_request = next(row["request"]["params"] for row in h.trace if row["request"]["id"] == "confirm-new")
    replay = h.invoke("requirement.confirm", confirm_request["payload"], "confirm-new",
        extra={"expected_heads": confirm_request["expected_heads"]})
    assert replay == confirmed
    if approved is not None:
        assert h.approve() == approved
    assert h.store.conn.execute("SELECT COUNT(*) FROM revision").fetchone()[0] == count
    response = h.raw("approval.decide", {**h.apply_payload(), "decision": "approved", "reason": "stale request"}, "stale-decide", human=True)
    assert _code(response) == "SNAPSHOT_CHANGED"
    approval = h.payload(h.latest("approval", h.approval["approval_id"]))
    h.observed.update(initial=initial, approval=approval, old_snapshot=h.snapshot, phase=h.phase(),
        original_approval_receipt=approved, publication_replay=confirmed, queries_and_replay_added_revisions=0)
    assert approval["status"] == "superseded"
    assert h.phase() == "delivery_ready"


def test_ac21_unrelated_task_name_and_audit_do_not_invalidate(delivery):
    h = delivery
    h.ready()
    h.request()
    current = h.payload(h.latest("task", h.task.object_id))
    h.seed("task", h.task.object_id, {**current, "display_name": "renamed only"})
    h.invoke("rules.preview", {"draft_ref": h.rules.to_dict(), "source_as_of": str(h.store.next_commit_seq() - 1)}, "audit-only")
    h.approve()
    approval = h.payload(h.latest("approval", h.approval["approval_id"]))
    assert approval["status"] == "approved"
    assert h.payload(h.snapshot_ref)["digest"] == h.snapshot["digest"]
    h.observed.update(approval=approval, snapshot_digest=h.snapshot["digest"])


def test_ac22_public_snapshot_digest_survives_approval_operation_and_archive(delivery):
    h = delivery
    h.ready()
    h.request()
    before = json.loads(json.dumps(h.snapshot["body"]))
    h.approve()
    applied = h.invoke("delivery.apply", h.apply_payload(), "apply")
    operation = h.latest("delivery", applied["operation_id"])
    closed = h.invoke("task.close", {"task_ref": h.task.to_dict(), "applied_operation_ref": operation.to_dict()}, "close")
    manifest = closed["object_refs"][1]
    archived = h.invoke("archive.export", {"manifest_ref": manifest, "sink_id": "exports"}, "archive")
    assert h.operation(archived["operation_id"])["status"] == "succeeded"
    snapshot = h.payload(h.snapshot_ref)
    assert snapshot["body"] == before and snapshot["digest"] == sha256_digest(before)
    assert "approval" not in before and "operation_id" not in before
    h.observed.update(snapshot=snapshot, archive_manifest=h.payload(ObjectRef.from_dict(manifest)), archive_status=h.query("archive.status", {"manifest_ref": manifest}))


@pytest.mark.parametrize("point", ["before_claim", "after_claim", "after_start", "after_effect"])
def test_ac23_public_crash_points_reconcile_without_blind_effect_replay(delivery, monkeypatch, point):
    h = delivery
    h.ready()
    h.request()
    h.approve()
    original_export = h.exporter.export
    def export(*args, **kwargs):
        h.calls.append(args[0].manifest_id)
        return original_export(*args, **kwargs)
    monkeypatch.setattr(h.exporter, "export", export)
    execute = UnitOfWork.execute
    def crash(self, callback):
        command = {"before_claim": "delivery.apply", "after_claim": "delivery.apply",
            "after_start": "delivery.apply", "after_effect": "delivery.settle"}[point]
        if self.command_kind == command and (point != "after_start" or self.ctx.idempotency_key.startswith("apply-crash:start:")):
            if point in {"after_claim", "after_start"}:
                execute(self, callback)
            raise OSError("isolated crash point: " + point)
        return execute(self, callback)
    monkeypatch.setattr(UnitOfWork, "execute", crash)
    response = h.raw("delivery.apply", h.apply_payload(), "apply-crash")
    assert _code(response) == "TEMPORARY_UNAVAILABLE"
    monkeypatch.setattr(UnitOfWork, "execute", execute)
    receipt = h.invoke("delivery.apply", h.apply_payload(), "apply-crash")
    oid = receipt["operation_id"]
    calls_before = list(h.calls)
    h.invoke("delivery.reconcile", {"operation_id": oid}, "reconcile")
    state = h.operation(oid)
    assert h.invoke("delivery.apply", h.apply_payload(), "apply-crash") == receipt
    assert h.query("command.receipt", {"receipt_domain": "project", "idempotency_key": "apply-crash"})["receipt"] == receipt
    assert h.calls == calls_before
    assert state["status"] == {"before_claim": "applied", "after_claim": "claimed", "after_start": "unknown", "after_effect": "applied"}[point]
    assert len(h.calls) == (1 if point in {"before_claim", "after_effect"} else 0)
    h.observed.update(crash_point=point, original_error=response, receipt=receipt, operation=state, effect_calls=h.calls)


def test_ac24_public_old_epoch_settlement_is_ignored(delivery, monkeypatch):
    h = delivery
    h.ready()
    h.request()
    h.approve()
    original_apply = h.provider.apply
    def late(manifest, sink, oid):
        receipt = original_apply(manifest, sink, oid)
        current = h.payload(h.latest("delivery", oid))
        h.seed("delivery", oid, {**current, "epoch": 2})
        return receipt
    monkeypatch.setattr(h.provider, "apply", late)
    applied = h.invoke("delivery.apply", h.apply_payload(), "apply")
    operation = h.operation(applied["operation_id"])
    assert operation["epoch"] == 2 and operation["status"] == "applying"
    assert h.store.conn.execute("SELECT COUNT(*) FROM audit_event WHERE event_type='delivery.late_settlement'").fetchone()[0] == 1
    h.observed.update(operation=operation, late_settlement_audited=True)


def test_ac24_public_started_without_fence_stays_unknown_and_revocation_is_factful(delivery, monkeypatch):
    h = delivery
    h.ready()
    h.request()
    h.approve()
    def no_effect(manifest, sink, oid):
        return {"state": "unknown", "manifest_id": oid, "sink_id": sink, "digest": manifest.digest()}
    monkeypatch.setattr(h.provider, "apply", no_effect)
    applied = h.invoke("delivery.apply", h.apply_payload(), "apply")
    oid = applied["operation_id"]
    assert h.operation(oid)["status"] == "unknown"
    revoke = h.raw("approval.revoke", {**h.apply_payload(), "reason": "withdraw after start"}, "revoke", human=True)
    assert _code(revoke) == "CANCEL_PENDING"
    approval = h.payload(h.latest("approval", h.approval["approval_id"]))
    assert approval["status"] == "approved" and approval["apply_started"] is True
    h.invoke("delivery.reconcile", {"operation_id": oid}, "reconcile")
    assert h.operation(oid)["status"] == "unknown"
    h.observed.update(operation=h.operation(oid), approval=approval, exported_effect_exists=(h.root / "exports" / oid).exists())


@pytest.mark.parametrize("conflict", [False, True])
def test_ac25_public_real_bundle_complete_idempotent_and_conflict_preserved(delivery, monkeypatch, conflict):
    h = delivery
    h.ready()
    h.request()
    h.approve()
    oid = "operation-" + sha256_digest({"principal": "machine-test", "apply": "apply"})[:20]
    target = h.root / "exports" / oid
    if conflict:
        target.mkdir()
        (target / "manifest.json").write_bytes(b'{"foreign":"do not overwrite"}\n')
    original = h.exporter.export
    def counted(*args, **kwargs):
        h.calls.append(args[0].manifest_id)
        return original(*args, **kwargs)
    monkeypatch.setattr(h.exporter, "export", counted)
    first = h.invoke("delivery.apply", h.apply_payload(), "apply")
    before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    assert h.invoke("delivery.apply", h.apply_payload(), "apply") == first
    h.invoke("delivery.reconcile", {"operation_id": oid}, "reconcile")
    assert {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()} == before
    assert h.calls == [oid]
    if conflict:
        assert h.operation(oid)["status"] == "unknown"
        assert before == {"manifest.json": b'{"foreign":"do not overwrite"}\n'}
    else:
        assert h.operation(oid)["status"] == "applied"
        assert (target / "artifacts" / h.artifact.sha256).read_bytes() == b"G2 isolated deliverable\n"
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["snapshot_digest"] == h.snapshot["digest"]
        assert manifest["artifacts"] == [h.artifact.to_dict()]
    h.observed.update(conflict=conflict, operation=h.operation(oid), effect_calls=h.calls)


@pytest.mark.parametrize("damage", ["staged_only", "missing", "changed"])
def test_ac26_public_request_cannot_freeze_unready_missing_or_changed_artifact(delivery, damage):
    h = delivery
    h.ready()
    path = h.storage._ready_path(h.artifact.sha256)
    if damage == "changed":
        path.write_bytes(b"mutated content")
    else:
        path.unlink()
        if damage == "staged_only":
            h.storage.stage(b"G2 isolated deliverable\n", "text/plain")
    rejected = h.raw("delivery.request", h.request_payload(), "request-unready")
    assert _code(rejected) == ("ARTIFACT_DIGEST_MISMATCH" if damage == "changed" else "ARTIFACT_MISSING")
    assert h.store.conn.execute("SELECT COUNT(*) FROM revision WHERE type IN ('delivery_snapshot','approval')").fetchone()[0] == 0
    assert h.phase() == "delivery_ready"
    h.observed.update(damage=damage, rejected=rejected, quarantine=h.storage.quarantine_entries(), phase=h.phase())
