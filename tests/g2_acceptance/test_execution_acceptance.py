"""G2 AC12-17 through the configured public RPC, with isolated raw evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import pytest

from project_kernel.bootstrap import build_server, InvocationContextRegistry
from project_kernel.contracts import ALL_CAPABILITIES, sha256_digest, compute_bundle_digest
from project_kernel.contracts.dto import CheckResult, ObjectRef, ProviderCapabilities
from project_kernel.evidence import ArtifactStorage
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.internal.environment_provider import PythonEnvironmentProbe
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, seed
from p03_attempt.fixture_executor import FixtureSubprocessExecutor


class Scenario:
    """Capture public request/response bytes and explicitly labelled host fixtures."""

    def __init__(self, root, nodeid):
        self.root = root
        self.nodeid = nodeid
        self.store = make_store(root, project_id="proj-a")
        self.calls = []
        self.observations = {}
        self.servers = []
        self.seeds = []

    def server(self, *, mode="test", **kwargs):
        registry = InvocationContextRegistry(handle_factory=lambda: "execution-review-context")
        registry.mint("g2-reviewer", ALL_CAPABILITIES, project_id="proj-a")
        server = build_server(self.store, principal="g2-reviewer", contexts=registry,
                              mode=mode, artifact_root=self.root / "artifacts", **kwargs)
        self.servers.append({"mode": mode, "entry": "build_server",
                             "executor": type(kwargs.get("executor")).__name__,
                             "environment_provider": type(kwargs.get("environment_provider")).__name__,
                             "check_provider": type(kwargs.get("check_provider")).__name__})
        request = {"jsonrpc": "2.0", "id": "initialize-" + str(len(self.calls)),
                   "method": "kernel.initialize", "params": {"client_id": "g2-execution-reviewer",
                   "supported_protocol_versions": ["1.0.0"]}}
        response = decode_frame(server.handle_line(encode_frame(request)))
        self.calls.append({"request": request, "response": response})
        assert "error" not in response, response
        assert response["result"]["mode"] == mode
        assert response["result"]["schema_bundle_digest"] == compute_bundle_digest()
        return server

    def raw(self, server, name, payload, key=None, *, query=False, selector=None, **extra):
        params = {"protocol_version": "1.0.0", "invocation_context_id": "execution-review-context",
                  "selector": {"project_id": selector or "proj-a"}, "payload": payload}
        if query:
            params["query"] = name
        else:
            params.update(command=name, expected_heads=[], idempotency_key=key or name)
        params.update(extra)
        request = {"jsonrpc": "2.0", "id": "execution-" + str(len(self.calls)),
                   "method": "kernel.query" if query else "kernel.command", "params": params}
        request_bytes = encode_frame(request)
        response_bytes = server.handle_line(request_bytes)
        response = decode_frame(response_bytes)
        self.calls.append({"request": request, "response": response,
                           "request_frame": request_bytes.decode("utf-8"),
                           "response_frame": response_bytes.decode("utf-8")})
        return response

    def command(self, server, name, payload, key=None, **extra):
        response = self.raw(server, name, payload, key, **extra)
        assert "error" not in response, response
        receipt = response["result"]["receipt"]
        assert receipt["status"] != "rejected", receipt
        return receipt

    def query(self, server, name, payload):
        response = self.raw(server, name, payload, query=True)
        assert "error" not in response, response
        return response["result"]

    def rejection(self, server, name, payload, key, expected):
        response = self.raw(server, name, payload, key)
        error = response.get("error", {}).get("data")
        if error is None:
            receipt = response["result"]["receipt"]
            assert receipt["status"] == "rejected", response
            error = receipt["error"]
        assert error["code"] in expected, response
        return error

    def seed(self, kind, oid, body):
        ref = seed(self.store, kind, oid, body)
        self.seeds.append({"ref": ref.to_dict(), "purpose": "explicit host-owned fixture",
                           "payload": body})
        return ref

    def prepare(self, server, **kwargs):
        before = set(row[0] for row in self.store.conn.execute("SELECT command_id FROM command_receipt"))
        prepared = prepare_dispatch(self.store, self.root,
            invoke=lambda command, payload, key: self.command(server, command, payload, key), **kwargs)
        self.observations.setdefault("dispatch_inputs", []).append({
            key: value.to_dict() if isinstance(value, ObjectRef) else
                 {strategy: ref.to_dict() for strategy, ref in value.items()} if key == "roots" else value
            for key, value in prepared.items()})
        self.observations.setdefault("fixture_seed_note", []).append({
            "description": "prepare_dispatch seeds budget, network_policy, execution_root, recipe and design_decision only; business design/rules/dispatch/environment use public RPC",
            "receipts_before": sorted(before)})
        return prepared

    def current(self, kind, oid):
        head = self.store.get_head(kind, oid, "current")
        assert head is not None
        return ObjectRef("proj-a", kind, oid, head["revision_id"])

    def operation(self, server, receipt):
        return self.query(server, "operation.status", {"operation_id": receipt["operation_id"]})["data"]

    def finish(self):
        revisions = []
        for kind, oid, revision in self.store.conn.execute(
                "SELECT type,object_id,revision_id FROM revision ORDER BY commit_seq,ordinal"):
            ref = ObjectRef("proj-a", kind, oid, revision)
            revisions.append({"ref": ref.to_dict(), **self.store.get_revision(ref)})
        roots = {"test_root": str(self.root.resolve()),
                 "database": str((self.root / "proj-a.sqlite").resolve()),
                 "artifacts": str((self.root / "artifacts").resolve()), "mode": "test"}
        live_sqlite_files = [{"path": str(path), "size": path.stat().st_size}
            for path in sorted(self.root.glob("*.sqlite*")) if path.is_file()]
        self.store.close()
        files = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.name != "execution-evidence.json":
                files.append({"path": str(path.relative_to(self.root)),
                              "size": path.stat().st_size,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "archive_bytes": ".sqlite" not in path.name})
        (self.root / "execution-evidence.json").write_text(json.dumps({
            "nodeid": self.nodeid, "roots": roots, "live_sqlite_files": live_sqlite_files,
            "public_entries": self.servers, "host_fixture_seeds": self.seeds,
            "requests": self.calls, "revisions": revisions, "observations": self.observations,
            "files": files, "limits": ["synthetic trusted identities", "no DSH or paid models",
                "fixture subprocess isolation is directory_only, not an OS sandbox"]},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def scenario(tmp_path, request):
    value = Scenario(tmp_path, request.node.nodeid)
    try:
        yield value
    finally:
        value.finish()


def start_payload(prepared, strategy="s1"):
    return {"packet_ref": prepared["packet"].to_dict(), "strategy_id": strategy,
            "execution_root_ref": prepared["roots"][strategy].to_dict()}


def test_ac12_rpc_packet_freezes_baselines_and_confirm_only_dispatch_ready(scenario):
    server = scenario.server(environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server, confirm=False)
    packet_before = scenario.store.get_revision(prepared["packet"])
    assert scenario.store.get_head("execution_packet", prepared["packet"].object_id, "current") is None
    scenario.rejection(server, "dispatch.confirm", {
        "draft_ref": prepared["packet"].to_dict(), "expected_baseline_digest": "f" * 64},
        "wrong-baseline", {"SNAPSHOT_CHANGED"})
    confirmed = scenario.command(server, "dispatch.confirm", {
        "draft_ref": prepared["packet"].to_dict(), "expected_baseline_digest": sha256_digest(prepared["body"])},
        "confirm-exact")
    assert scenario.store.get_revision(prepared["packet"]) == packet_before
    task = scenario.store.get_revision(scenario.current("task", prepared["task"].object_id))["payload"]
    assert task["phase"] == "dispatch_ready"
    assert not scenario.store.conn.execute("SELECT 1 FROM revision WHERE type='attempt'").fetchone()
    empty = scenario.command(server, "rules.save", {"ruleset_id": prepared["rules"].object_id,
        "data_rules": [], "reason": "new publication must not mutate old packet"}, "next-rule-draft",
        expected_heads=[{"object_ref": prepared["rules"].to_dict(), "pointer_name": "draft",
            "expected_head_version": str(scenario.store.get_head("rules", prepared["rules"].object_id, "draft")["head_version"])}])
    draft = empty["object_refs"][0]
    preview = scenario.command(server, "rules.preview", {"draft_ref": draft,
        "source_as_of": str(scenario.store.next_commit_seq() - 1)}, "next-rule-preview")
    scenario.command(server, "rules.publish", {"draft_ref": draft,
        "impact_preview_ref": preview["object_refs"][0]}, "next-rule-publish",
        expected_heads=[{"object_ref": prepared["rules"].to_dict(), "pointer_name": "current",
            "expected_head_version": str(scenario.store.get_head("rules", prepared["rules"].object_id, "current")["head_version"])}])
    assert scenario.store.get_revision(prepared["packet"]) == packet_before
    assert packet_before["payload"]["scope"] == prepared["scope"]
    assert packet_before["payload"]["acceptance_refs"] == [prepared["acceptance"].to_dict()]
    assert packet_before["payload"]["rule_refs"] == [prepared["rules"].to_dict()]
    scenario.observations["AC12"] = {"packet_before_and_after": packet_before,
        "confirmation_receipt": confirmed, "task_after_confirm": task,
        "old_rules_ref": prepared["rules"].to_dict(), "new_rules_ref": draft}


@pytest.mark.parametrize("invalid", ["path", "expression", "operator"])
def test_ac13_rpc_rejects_illegal_fact_path_and_expression(scenario, invalid):
    server = scenario.server()
    condition = {"path": "mode", "operator": "eq", "value": "test"}
    if invalid == "path":
        condition["path"] = "environment.__class__"
    elif invalid == "expression":
        condition = {"expression": "__import__('os').system('echo forbidden')"}
    else:
        condition["operator"] = "eval"
    scenario.rejection(server, "rules.save", {"ruleset_id": "invalid-rule", "data_rules": [{
        "rule_id": "deny-1", "enabled": True, "when": condition,
        "effect": "deny", "reason": "invalid fixture"}], "reason": "invalid expression fixture"},
        "invalid-rule", {"INVALID_INPUT"})
    assert scenario.store.get_head("rules", "invalid-rule", "draft") is None


def test_ac13_rpc_unknown_deny_blocks_and_disabled_data_rules_cannot_disable_redlines(scenario):
    server = scenario.server(environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server, confirm=False)
    saved = scenario.command(server, "rules.save", {"ruleset_id": "unknown-policy", "data_rules": [{
        "rule_id": "provider-guarantee", "enabled": True,
        "when": {"path": "provider.supported_sandbox_level", "operator": "eq", "value": "os_enforced"},
        "effect": "deny", "reason": "provider fact absent"}], "reason": "unknown is not permission"}, "unknown-save")
    rule = saved["object_refs"][0]
    preview = scenario.command(server, "rules.preview", {"draft_ref": rule,
        "source_as_of": str(scenario.store.next_commit_seq() - 1)}, "unknown-preview")
    preview_body = scenario.store.get_revision(ObjectRef.from_dict(preview["object_refs"][0]))["payload"]
    assert preview_body["impacts"][0]["blocked"]
    assert preview_body["impacts"][0]["decisions"] == ["deny-unknown:provider-guarantee"]
    scenario.command(server, "rules.publish", {"draft_ref": rule,
        "impact_preview_ref": preview["object_refs"][0]}, "unknown-publish")
    body = deepcopy(prepared["body"])
    body["rule_refs"] = [rule]
    draft = scenario.command(server, "dispatch.draft", body, "unknown-packet")["object_refs"][0]
    scenario.rejection(server, "dispatch.confirm", {"draft_ref": draft,
        "expected_baseline_digest": sha256_digest(body)}, "unknown-confirm", {"REQUIRED_FACT_UNKNOWN"})
    disabled = scenario.command(server, "rules.save", {"ruleset_id": "disabled-data-policy", "data_rules": [{
        "rule_id": "approval-bypass", "enabled": False,
        "when": {"path": "mode", "operator": "eq", "value": "test"},
        "effect": "require_human", "reason": "disabled optional policy"}], "reason": "optional policy disabled"}, "disabled-save")
    preview = scenario.command(server, "rules.preview", {"draft_ref": disabled["object_refs"][0],
        "source_as_of": str(scenario.store.next_commit_seq() - 1)}, "disabled-preview")
    scenario.command(server, "rules.publish", {"draft_ref": disabled["object_refs"][0],
        "impact_preview_ref": preview["object_refs"][0]}, "disabled-publish")
    scenario.rejection(server, "approval.decide", {"approval_id": "synthetic-missing", "snapshot_digest": "a" * 64,
        "decision": "approved", "reason": "disabled policy does not grant approval"},
        "cannot-approve", {"UNSUPPORTED_COMMAND"})
    foreign = deepcopy(body)
    foreign["task_ref"]["project_id"] = "proj-b"
    scenario.rejection(server, "dispatch.draft", foreign, "cannot-disable-scope", {"SCOPE_MISMATCH"})
    scenario.observations["AC13"] = {"unknown_preview": preview_body,
        "redlines": ["machine approval commands remain unavailable", "project references remain scoped"]}


def test_ac14_rpc_missing_execution_and_check_providers_do_not_complete_or_pass(scenario):
    server = scenario.server(environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server)
    scenario.rejection(server, "attempt.start", start_payload(prepared), "missing-executor", {"CAPABILITY_UNAVAILABLE"})
    assert not scenario.store.conn.execute("SELECT 1 FROM revision WHERE type='attempt'").fetchone()
    executor = FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('actual subprocess')"]})
    running = scenario.server(executor=executor)
    receipt = scenario.command(running, "attempt.start", start_payload(prepared), "real-attempt")
    attempt = scenario.current("attempt", receipt["operation_id"])
    candidate = scenario.seed("candidate_manifest", "candidate-no-check", {
        "attempt_ref": attempt.to_dict(), "candidate_digest": "a" * 64, "artifacts": []})
    verification = scenario.command(running, "verification.run", {"attempt_ref": attempt.to_dict(),
        "candidate_manifest_ref": candidate.to_dict(), "acceptance_refs": [prepared["acceptance"].to_dict()]}, "no-check")
    report = scenario.store.get_revision(ObjectRef.from_dict(verification["object_refs"][0]))["payload"]
    assert report["passed"] is False and report["result"] == "incomplete"
    assert report["checks"] == []
    scenario.observations["AC14"] = {"actual_attempt": scenario.operation(running, receipt), "unchecked_report": report}


def test_ac14_rpc_production_verification_rejects_test_checks_and_freeze(scenario):
    server = scenario.server(environment_provider=PythonEnvironmentProbe(),
        executor=FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('fixture')"]}))
    prepared = scenario.prepare(server)
    started = scenario.command(server, "attempt.start", start_payload(prepared), "simulation-attempt")
    attempt = scenario.current("attempt", started["operation_id"])
    storage = ArtifactStorage(scenario.root / "artifacts")
    artifact = storage.publish(storage.stage(b"simulated candidate", "text/plain"), "text/plain")
    candidate = scenario.seed("candidate_manifest", "sim-candidate", {
        "attempt_ref": attempt.to_dict(), "candidate_digest": "c" * 64, "artifacts": [artifact.to_dict()]})

    def test_checks(items):
        return [CheckResult(item.item_id, item.recipe_ref, candidate_digest="c" * 64,
                            result="pass", evidence_mode="test") for item in items]

    production = scenario.server(mode="production", check_provider=test_checks)
    report_receipt = scenario.command(production, "verification.run", {"attempt_ref": attempt.to_dict(),
        "candidate_manifest_ref": candidate.to_dict(), "acceptance_refs": [prepared["acceptance"].to_dict()]}, "production-check")
    report = scenario.store.get_revision(ObjectRef.from_dict(report_receipt["object_refs"][0]))["payload"]
    assert report["passed"] is False and "simulation" in " ".join(report["reasons"])
    selection = scenario.seed("selection", "fixture-selection", {"purpose": "delivery",
        "attempt_ref": attempt.to_dict(), "verification_refs": report_receipt["object_refs"],
        "reason": "host fixture solely to test freeze rejection"})
    target = scenario.seed("delivery_target", "fixture-target", {"method": "bundle", "sink_id": "exports"})
    scenario.rejection(production, "delivery.request", {"selection_ref": selection.to_dict(),
        "candidate_ref": candidate.to_dict(), "target_ref": target.to_dict()}, "formal-freeze", {"VERIFICATION_FAILED"})
    assert not scenario.store.conn.execute("SELECT 1 FROM revision WHERE type='delivery_snapshot'").fetchone()
    scenario.observations["AC14"] = {"production_report": report, "freeze_snapshot_count": 0}


def test_ac14_rpc_production_cannot_relabel_test_attempt_for_formal_freeze(scenario):
    server = scenario.server(environment_provider=PythonEnvironmentProbe(),
        executor=FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('test evidence')"]}))
    prepared = scenario.prepare(server)
    started = scenario.command(server, "attempt.start", start_payload(prepared), "test-attempt")
    attempt = scenario.current("attempt", started["operation_id"])
    storage = ArtifactStorage(scenario.root / "artifacts")
    artifact = storage.publish(storage.stage(b"test candidate", "text/plain"), "text/plain")
    candidate = scenario.seed("candidate_manifest", "relabel-candidate", {
        "attempt_ref": attempt.to_dict(), "candidate_digest": "d" * 64, "artifacts": [artifact.to_dict()]})

    def production_checks(items):
        return [CheckResult(item.item_id, item.recipe_ref, candidate_digest="d" * 64,
                            result="pass", evidence_mode="production") for item in items]

    production = scenario.server(mode="production", check_provider=production_checks)
    report_receipt = scenario.command(production, "verification.run", {"attempt_ref": attempt.to_dict(),
        "candidate_manifest_ref": candidate.to_dict(), "acceptance_refs": [prepared["acceptance"].to_dict()]}, "claimed-production-check")
    report = scenario.store.get_revision(ObjectRef.from_dict(report_receipt["object_refs"][0]))["payload"]
    selection_receipt = scenario.command(production, "attempt.select", {
        "purpose": "delivery", "attempt_ref": attempt.to_dict(), "comparison_refs": [attempt.to_dict()],
        "reason": "production checker cannot change persisted execution mode"}, "relabel-selection")
    selection = ObjectRef.from_dict(selection_receipt["object_refs"][0])
    target = scenario.seed("delivery_target", "relabel-target", {"method": "bundle", "sink_id": "exports"})
    scenario.rejection(production, "delivery.request", {"selection_ref": selection.to_dict(),
        "candidate_ref": candidate.to_dict(), "target_ref": target.to_dict()}, "relabel-formal-freeze",
        {"SIMULATION_EVIDENCE", "VERIFICATION_FAILED", "EVIDENCE_STALE"})
    assert not scenario.store.conn.execute("SELECT 1 FROM revision WHERE type='delivery_snapshot'").fetchone()
    scenario.observations["AC14"] = {"report_with_claimed_production_checks": report,
        "persisted_attempt_mode": scenario.store.get_revision(attempt)["payload"]["mode"],
        "persisted_packet_mode": scenario.store.get_revision(prepared["packet"])["payload"]["mode"]}


def test_ac15_rpc_cross_project_and_strategy_root_rejected_real_writes_isolated(scenario):
    executor = FixtureSubprocessExecutor({strategy: [sys.executable, "-c",
        "from pathlib import Path; Path('output.txt').write_text('" + strategy + "'); print('" + strategy + "')"]
        for strategy in ("s1", "s2")})
    server = scenario.server(executor=executor, environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server, strategies=("s1", "s2"))
    foreign = start_payload(prepared)
    foreign["packet_ref"]["project_id"] = "proj-b"
    scenario.rejection(server, "attempt.start", foreign, "foreign-packet", {"SCOPE_MISMATCH"})
    wrong_root = start_payload(prepared)
    wrong_root["execution_root_ref"] = prepared["roots"]["s2"].to_dict()
    scenario.rejection(server, "attempt.start", wrong_root, "wrong-strategy-root", {"INVALID_INPUT"})
    attempts = []
    for strategy in ("s1", "s2"):
        receipt = scenario.command(server, "attempt.start", start_payload(prepared, strategy), "start-" + strategy)
        outcome = scenario.operation(server, receipt)
        assert outcome["status"] == "completed"
        assert outcome["task_ref"] == prepared["task"].to_dict()
        assert outcome["provider_capabilities"]["supported_sandbox_level"] == "directory_only"
        assert outcome["strategy_id"] == strategy
        assert (scenario.root / strategy / "output.txt").read_text() == strategy
        attempts.append(outcome)
    assert prepared["roots"]["s1"] != prepared["roots"]["s2"]
    comparison = scenario.query(server, "attempts.compare", {"task_ref": prepared["task"].to_dict()})
    assert len(comparison["data"]["attempts"]) == 2
    scenario.observations["AC15"] = {"attempts": attempts, "comparison": comparison,
        "guarantee": "real subprocess cwd separation; no OS sandbox claim"}


@pytest.mark.parametrize("overlap", ["same", "ancestor", "descendant"])
def test_ac15_rpc_refuses_different_strategy_aliasing_same_directory(scenario, overlap):
    server = scenario.server(environment_provider=PythonEnvironmentProbe(),
        executor=FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('first')"],
                                             "s2": [sys.executable, "-c", "print('second')"]}))
    prepared = scenario.prepare(server, strategies=("s1", "s2"))
    if overlap == "ancestor":
        root = scenario.root / "s1" / "nested"
        root.mkdir()
        prepared["roots"]["s1"] = scenario.seed("execution_root", "nested-s1-root", {
            "path": str(root.resolve()), "task_ref": prepared["task"].to_dict(),
            "strategy_id": "s1", "parent_ref": prepared["body"]["scope"]["execution_root_ref"]})
    scenario.command(server, "attempt.start", start_payload(prepared), "first-strategy")
    second_root = scenario.root / "s1"
    if overlap == "descendant":
        second_root = second_root / "nested"
        second_root.mkdir()
    aliased = scenario.seed("execution_root", "aliased-s2-root", {
        "path": str(second_root.resolve()), "task_ref": prepared["task"].to_dict(),
        "strategy_id": "s2", "parent_ref": prepared["body"]["scope"]["execution_root_ref"]})
    payload = start_payload(prepared, "s2")
    payload["execution_root_ref"] = aliased.to_dict()
    scenario.rejection(server, "attempt.start", payload, "aliased-second-strategy", {"INVALID_INPUT"})


@pytest.mark.parametrize("status", ["running", "unknown"])
@pytest.mark.parametrize("overlap", ["same", "ancestor", "descendant"])
def test_ac15_rpc_live_directory_reservation_survives_root_revision_and_restart(scenario, status, overlap):
    class LiveExecutor:
        def __init__(self):
            self.calls = 0

        def capabilities(self):
            return ProviderCapabilities("live-test-provider", ("run",), "directory_only")

        def run(self, strategy, root):
            self.calls += 1
            return {"status": status, "stdout": b"live directory reservation", "stderr": b""}

    executor = LiveExecutor()
    server = scenario.server(executor=executor, environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server)
    original_path = scenario.root / "s1"
    if overlap == "ancestor":
        original_path /= "nested"
        original_path.mkdir()
        prepared["roots"]["s1"] = scenario.seed("execution_root", "live-s1-root", {
            "path": str(original_path.resolve()), "task_ref": prepared["task"].to_dict(),
            "strategy_id": "s1", "parent_ref": prepared["body"]["scope"]["execution_root_ref"]})
    started = scenario.command(server, "attempt.start", start_payload(prepared), "live-attempt")
    persisted_ref = prepared["roots"]["s1"]
    historical = scenario.store.get_revision(persisted_ref)
    changed_path = scenario.root / "changed-root"
    changed_path.mkdir()
    scenario.seed("execution_root", persisted_ref.object_id, {
        "path": str(changed_path.resolve()), "task_ref": prepared["task"].to_dict(),
        "strategy_id": "s1", "parent_ref": prepared["body"]["scope"]["execution_root_ref"]})
    candidate_path = scenario.root / "s1"
    if overlap == "descendant":
        candidate_path /= "nested"
        candidate_path.mkdir()
    alias = scenario.seed("execution_root", "live-alias", {
        "path": str(candidate_path.resolve()), "task_ref": prepared["task"].to_dict(),
        "strategy_id": "s1", "parent_ref": prepared["body"]["scope"]["execution_root_ref"]})
    scenario.store.close()
    scenario.store = make_store(scenario.root, project_id="proj-a")
    restarted = scenario.server(executor=executor)
    assert scenario.store.get_revision(persisted_ref) == historical
    assert scenario.operation(restarted, started)["status"] == status
    payload = {**start_payload(prepared), "execution_root_ref": alias.to_dict()}
    error = scenario.rejection(restarted, "attempt.start", payload, "live-alias-rejected", {"INVALID_INPUT"})
    assert scenario.rejection(restarted, "attempt.start", payload, "live-alias-rejected", {"INVALID_INPUT"}) == error
    assert executor.calls == 1
    scenario.observations["AC15"] = {"reserved_old_root_ref": persisted_ref.to_dict(),
        "historical_root": historical, "live_status": status, "overlap": overlap,
        "provider_calls_after_reconnect_replay": executor.calls}


def test_ac15_rpc_same_strategy_cross_task_cannot_reuse_directory(scenario):
    executor = FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('same strategy')"]})
    server = scenario.server(executor=executor, environment_provider=PythonEnvironmentProbe())
    first = scenario.prepare(server)
    scenario.command(server, "attempt.start", start_payload(first), "original-task")
    second = scenario.prepare(server, prefix="other-")
    assert second["task"].object_id != first["task"].object_id
    scenario.rejection(server, "attempt.start", start_payload(second), "other-task-same-directory", {"INVALID_INPUT"})


def test_ac16_rpc_unconfirmed_cancel_stays_unknown_pending_without_replay(scenario):
    class UnknownExecutor:
        def __init__(self):
            self.calls = 0

        def capabilities(self):
            return ProviderCapabilities("unknown-test-provider", ("run",), "directory_only")

        def run(self, strategy, root):
            self.calls += 1
            return {"status": "unknown", "stdout": b"observation incomplete", "stderr": b"", "exit_code": None}

    executor = UnknownExecutor()
    server = scenario.server(executor=executor, environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server)
    payload = start_payload(prepared)
    started = scenario.command(server, "attempt.start", payload, "unknown-start")
    assert scenario.command(server, "attempt.start", payload, "unknown-start") == started
    attempt = scenario.current("attempt", started["operation_id"])
    cancel_payload = {"attempt_ref": attempt.to_dict(), "reason": "reviewer asks to stop"}
    cancel = scenario.command(server, "attempt.cancel", cancel_payload, "unconfirmed-cancel")
    assert scenario.command(server, "attempt.cancel", cancel_payload, "unconfirmed-cancel") == cancel
    outcome = scenario.operation(server, started)
    assert outcome["status"] == "unknown" and outcome["cancel_status"] == "pending"
    assert executor.calls == 1
    scenario.rejection(server, "attempt.start", payload, "unknown-retry-same-root", {"INVALID_INPUT"})
    aliased = scenario.seed("execution_root", "unknown-root-alias", {
        "path": str((scenario.root / "s1").resolve()), "task_ref": prepared["task"].to_dict(),
        "strategy_id": "s1", "parent_ref": prepared["body"]["scope"]["execution_root_ref"]})
    alias_payload = {**payload, "execution_root_ref": aliased.to_dict()}
    scenario.rejection(server, "attempt.start", alias_payload, "unknown-retry-aliased-root", {"INVALID_INPUT"})
    assert executor.calls == 1
    scenario.observations["AC16"] = {"cancel_outcome": outcome, "provider_calls": executor.calls}


def test_ac16_rpc_retry_is_new_attempt_and_keeps_real_failure_outputs(scenario):
    executor = FixtureSubprocessExecutor({"s1": [sys.executable, "-c",
        "import sys; print('first failure'); print('error evidence',file=sys.stderr); raise SystemExit(7)"]})
    server = scenario.server(executor=executor, environment_provider=PythonEnvironmentProbe())
    prepared = scenario.prepare(server)
    payload = start_payload(prepared)
    failed = scenario.command(server, "attempt.start", payload, "failed-attempt")
    failed_ref = scenario.current("attempt", failed["operation_id"])
    failed_row = scenario.store.get_revision(failed_ref)
    assert failed_row["payload"]["status"] == "failed" and failed_row["payload"]["exit_code"] == 7
    executor.command_map["s1"] = [sys.executable, "-c", "print('repaired subprocess')"]
    repaired = scenario.command(server, "attempt.start", payload, "new-retry")
    assert repaired["operation_id"] != failed["operation_id"]
    assert scenario.operation(server, repaired)["status"] == "completed"
    assert scenario.store.get_revision(failed_ref) == failed_row
    storage = ArtifactStorage(scenario.root / "artifacts")
    from project_kernel.contracts.dto import ArtifactRef
    error_bytes = storage.open_read(ArtifactRef(**failed_row["payload"]["output_artifacts"]["stderr"]))
    assert b"error evidence" in error_bytes
    comparison = scenario.query(server, "attempts.compare", {"task_ref": prepared["task"].to_dict()})
    assert len(comparison["data"]["attempts"]) == 2
    scenario.observations["AC16"] = {"failure": failed_row, "retry": scenario.operation(server, repaired),
        "failure_error_sha256": hashlib.sha256(error_bytes).hexdigest(), "comparison": comparison}


def test_ac17_rpc_real_versions_paths_times_missing_old_unknown_and_no_install(scenario):
    provider = PythonEnvironmentProbe()
    server = scenario.server(environment_provider=provider)
    prepared = scenario.prepare(server)
    missing_name = "g2-round4-missing-package-aca09b0"
    before = sorted((item.metadata["Name"], item.version) for item in importlib.metadata.distributions())
    recipe = scenario.seed("recipe", "environment-state-fixture", {"dependencies": [
        {"name": "python", "version_spec": ">=3.10"},
        {"name": "python", "version_spec": ">=999"},
        {"name": missing_name, "version_spec": ">=1"},
        {"name": "python", "version_spec": "invalid-version-spec"}]})
    receipt = scenario.command(server, "environment.probe", {
        "task_ref": prepared["task"].to_dict(), "execution_root_ref": prepared["roots"]["s1"].to_dict(),
        "requirement_refs": [prepared["requirement"].to_dict()], "recipe_refs": [recipe.to_dict()]}, "environment-states")
    result = scenario.operation(server, receipt)
    assert result["status"] == "blocked"
    assert [fact["state"] for fact in result["facts"]] == ["satisfied", "too_old", "missing", "unknown"]
    for fact in result["facts"]:
        assert "required_version" in fact
        assert datetime.fromisoformat(fact["checked_at"]).tzinfo is not None
    assert result["facts"][0]["version"] and Path(result["facts"][0]["path"]).is_file()
    assert result["facts"][0]["path"] == sys.executable
    report = scenario.query(server, "environment.report", {"task_ref": prepared["task"].to_dict()})
    for state in ("satisfied", "too_old", "missing", "unknown"):
        assert len(report["data"][state]) == 1
    after = sorted((item.metadata["Name"], item.version) for item in importlib.metadata.distributions())
    assert before == after
    scenario.observations["AC17"] = {"environment_result": result, "environment_report": report,
        "distribution_inventory_sha256_before": sha256_digest(before),
        "distribution_inventory_sha256_after": sha256_digest(after),
        "no_install": "provider only queries platform/sys/importlib.metadata; no installer or subprocess"}
