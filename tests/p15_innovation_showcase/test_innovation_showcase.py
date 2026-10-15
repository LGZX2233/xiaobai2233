"""Innovation showcase: one scenario that exercises every module the AGH panel shows.

Everything goes through the public RPC entry with a real external solver subprocess
(evidence_mode=test, directory_only isolation, not an OS sandbox). Each numbered step
names the innovation it demonstrates:

  A ledger        immutable revisions, frozen read watermark, stale is reported, survives restart
  B unknown       a stalled provider settles as unknown, is retained, never relaunched
  C trust         independent recomputation, human-only approval, deny-only rules
  D idempotency   a repeated key returns the original receipt and does no second effect
  E invalidation  changing the candidate supersedes an earlier approval
  F delivery      applied is observed, reconcile never replays the write
  G views         the read models the AGH panel renders (tree, trace, coverage, env, timeline)
"""
import json
import sys
from pathlib import Path

import pytest

from project_kernel.application.environment_service import PythonEnvironmentProbe
from project_kernel.contracts.dto import ObjectRef
from project_kernel.evidence import ArtifactStorage, BundleExporter
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, seed
from p13_integration.auth_helpers import build_test_server
from p13_integration.test_closed_loop import call, latest
from p14_science_demo.science_checker import HeatCheckProvider
from p14_science_demo.science_executor import HeatInverseExecutor
from p14_science_demo.test_heat_inversion_flow import publish_candidate

PROJECT = "proj-showcase"
WORKER = str(Path(__file__).resolve().parents[1] / "p14_science_demo" / "heat_worker.py")
KERNEL_ROOT = Path(__file__).resolve().parents[2]


def argv(*args):
    return [sys.executable, "-I", WORKER, *args]


def raw(server, kind, name, payload, key=None, **extra):
    """Send one frame and return the decoded response without asserting success."""
    params = {"protocol_version": "1.0.0", "invocation_context_id": "ctx1",
              "selector": {"project_id": PROJECT}, "payload": payload}
    if kind == "query":
        params["query"] = name
    else:
        params.update(command=name, idempotency_key=key or name, expected_heads=[])
    params.update(extra)
    return decode_frame(server.handle_line(encode_frame({
        "jsonrpc": "2.0", "id": "r1", "method": f"kernel.{kind}", "params": params})))


def without_completeness(data):
    return {key: value for key, value in data.items() if key != "completeness"}


def refusal_code(response):
    if "error" in response:
        return response["error"]["data"]["code"]
    receipt = response["result"]["receipt"]
    assert receipt["status"] == "rejected", receipt
    return receipt["error"]["code"]


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "showcase"
    root.mkdir()
    store = make_store(root, project_id=PROJECT)
    storage = ArtifactStorage(root / "artifacts")
    exporter = BundleExporter(root / "exports", storage, allowed_sinks=("exports",))
    executor = HeatInverseExecutor(store, {
        "s1": argv("grid", "--step", "0.05"),
        "s2": argv("golden", "--iters", "30"),
        "s3": argv("stall", "--hang", "30"),
    }, poll_timeout=1.0)
    checks = HeatCheckProvider(store, storage)
    srv = build_test_server(store, executor=executor, artifact_root=root / "artifacts",
                            bundle_exporter=exporter, environment_provider=PythonEnvironmentProbe(),
                            check_provider=checks)
    human = build_test_server(store, human=True)
    invoke = lambda name, body, key: call(srv, PROJECT, name, body, key)
    query = lambda name, body=None, **extra: call(srv, PROJECT, name, body or {}, query=True, **extra)
    state = dict(root=root, store=store, storage=storage, exporter=exporter, executor=executor,
                 srv=srv, human=human, invoke=invoke, query=query)
    try:
        yield state
    finally:
        executor.close()
        state["store"].close()


def test_innovation_showcase(world, monkeypatch):
    root, store, storage = world["root"], world["store"], world["storage"]
    executor, srv, human = world["executor"], world["srv"], world["human"]
    invoke, query, exporter = world["invoke"], world["query"], world["exporter"]

    p = prepare_dispatch(store, root, strategies=("s1", "s2", "s3"), invoke=invoke)

    def start(strategy, key):
        data = {"packet_ref": p["packet"].to_dict(), "strategy_id": strategy,
                "execution_root_ref": p["roots"][strategy].to_dict()}
        receipt = invoke("attempt.start", data, key)
        return data, receipt, latest(store, "attempt", receipt["operation_id"])

    def verify(attempt, candidate, key):
        receipt = invoke("verification.run", {"attempt_ref": attempt.to_dict(),
            "candidate_manifest_ref": candidate.to_dict(),
            "acceptance_refs": [p["acceptance"].to_dict()]}, key)
        return store.get_revision(ObjectRef.from_dict(receipt["object_refs"][0]))["payload"]

    # ---- A ledger: freeze a watermark before any attempt exists -------------------------
    frozen_seq = str(store.next_commit_seq() - 1)
    frozen = query("project.overview", as_of_seq=frozen_seq)["data"]
    assert frozen["phases"], "the dispatched task is already in the ledger"

    # ---- B unknown: a stalled solver is unknown, retained and never relaunched ----------
    stall_data, stall_receipt, stalled = start("s3", "stall")
    assert store.get_revision(stalled)["payload"]["status"] == "unknown"
    launches_after_stall = executor.launches
    for _ in range(3):  # reading, polling status and comparing never relaunch
        query("operation.status", {"operation_id": stall_receipt["operation_id"]})
        query("attempts.compare", {"task_ref": p["task"].to_dict()})
    assert executor.launches == launches_after_stall

    # ---- D idempotency: the same key returns the original receipt, no second launch -----
    assert invoke("attempt.start", stall_data, "stall") == stall_receipt
    assert executor.launches == launches_after_stall

    # ---- normal samples: coarse grid misses tolerance, golden section passes ------------
    _, _, coarse = start("s1", "coarse")
    coarse_cand = publish_candidate(store, storage, coarse, root / "s1" / "result.json", "cand-coarse")
    assert verify(coarse, coarse_cand, "verify-coarse")["passed"] is False
    _, _, golden = start("s2", "golden")
    golden_cand = publish_candidate(store, storage, golden, root / "s2" / "result.json", "cand-golden")
    assert verify(golden, golden_cand, "verify-golden")["passed"] is True

    # ---- C trust: a forged fit fails the independent recomputation ----------------------
    forged = json.loads((root / "s2" / "result.json").read_text(encoding="utf-8"))
    forged["alpha_fit"] = 0.9
    forged_cand = publish_candidate(store, storage, golden, None, "cand-forged",
                                    raw=json.dumps(forged).encode())
    assert verify(golden, forged_cand, "verify-forged")["passed"] is False

    # ---- error statistics source: failures retained, missing usage is not zero ----------
    compare = query("attempts.compare", {"task_ref": p["task"].to_dict()})["data"]
    by_strategy = {a["strategy_id"]: a for a in compare["attempts"]}
    assert set(by_strategy) == {"s1", "s2", "s3"}
    assert by_strategy["s3"]["status"] == "unknown"
    assert stalled.object_id in compare["failures_retained"]
    assert compare["cost"]["missing_usage_is_not_zero"] is True and compare["cost"]["total"] is None
    assert compare["selected"] is None

    # ---- selection keeps the comparison, delivery opens a pending approval --------------
    selection = invoke("attempt.select", {"attempt_ref": golden.to_dict(),
        "comparison_refs": [stalled.to_dict(), coarse.to_dict(), golden.to_dict()],
        "purpose": "delivery", "reason": "golden section meets tolerance; coarse grid does not"},
        "select")["object_refs"][0]
    assert query("attempts.compare", {"task_ref": p["task"].to_dict()})["data"]["selected"]["basis"] == "explicit_selection"
    target = seed(store, "delivery_target", "bundle", {"method": "bundle", "sink_id": "exports"})
    request = invoke("delivery.request", {"selection_ref": selection,
        "candidate_ref": golden_cand.to_dict(), "target_ref": target.to_dict()}, "request")
    approval = store.get_revision(ObjectRef.from_dict(request["object_refs"][0]))["payload"]
    queue = query("approvals.queue")["data"]
    assert queue["pending_count"] == 1 and queue["queue"][0]["status"] == "pending"

    # ---- C trust: the machine channel cannot decide, the human entry can ----------------
    decide = {"approval_id": approval["approval_id"], "snapshot_digest": approval["snapshot_digest"],
              "decision": "approved", "reason": "reviewed fit against the closed form"}
    assert refusal_code(raw(srv, "command", "approval.decide", decide, "machine-approve")) == "UNSUPPORTED_COMMAND"
    call(human, PROJECT, "approval.decide", decide, "approve")
    assert query("approvals.queue", {"status": "approved"})["data"]["count"] == 1

    # ---- E invalidation: a changed candidate supersedes the earlier approval ------------
    changed = json.loads((root / "s2" / "result.json").read_text(encoding="utf-8"))
    changed["alpha_fit"] = round(changed["alpha_fit"] * 1.004, 6)  # still inside the 5% tolerance
    changed_cand = publish_candidate(store, storage, golden, None, golden_cand.object_id,
                                     raw=json.dumps(changed).encode())
    assert verify(golden, changed_cand, "verify-changed")["passed"] is True
    old = store.get_revision(latest(store, "approval", approval["approval_id"]))["payload"]
    assert old["status"] == "superseded"
    selection = invoke("attempt.select", {"attempt_ref": golden.to_dict(),
        "comparison_refs": [stalled.to_dict(), coarse.to_dict(), golden.to_dict()],
        "purpose": "delivery", "reason": "re-verified candidate selected"}, "select-changed")["object_refs"][0]
    request = invoke("delivery.request", {"selection_ref": selection,
        "candidate_ref": changed_cand.to_dict(), "target_ref": target.to_dict()}, "request-changed")
    approval = store.get_revision(ObjectRef.from_dict(request["object_refs"][0]))["payload"]
    call(human, PROJECT, "approval.decide", {"approval_id": approval["approval_id"],
        "snapshot_digest": approval["snapshot_digest"], "decision": "approved",
        "reason": "reviewed the changed candidate"}, "approve-changed")

    # ---- F delivery: applied is observed, reconcile never replays the write -------------
    applied = invoke("delivery.apply", {"approval_id": approval["approval_id"],
        "snapshot_digest": approval["snapshot_digest"]}, "apply")
    assert query("operation.status", {"operation_id": applied["operation_id"]})["data"]["status"] == "applied"
    monkeypatch.setattr(exporter, "export", lambda *a, **k: pytest.fail("reconcile must not apply twice"))
    invoke("delivery.reconcile", {"operation_id": applied["operation_id"]}, "reconcile")
    assert query("operation.status", {"operation_id": applied["operation_id"]})["data"]["status"] == "applied"

    # ---- C trust: rules can only tighten, unknown facts block, no allow effect ----------
    rule = {"rule_id": "provider-guarantee", "enabled": True,
            "when": {"path": "provider.supported_sandbox_level", "operator": "eq", "value": "os_enforced"},
            "effect": "deny", "reason": "unknown provider fact must block"}
    saved = invoke("rules.save", {"ruleset_id": "showcase-rules", "data_rules": [rule],
                                  "reason": "unknown is not permission"}, "rules-save")
    assert saved["status"] != "rejected"
    allow = dict(rule, rule_id="allow-all", effect="allow")
    assert refusal_code(raw(srv, "command", "rules.save", {"ruleset_id": "showcase-allow",
        "data_rules": [allow], "reason": "allow must not exist"}, "rules-allow")) == "INVALID_INPUT"
    bad_path = dict(rule, rule_id="arbitrary", when={"path": "os.environ.SECRET", "operator": "eq", "value": 1})
    assert refusal_code(raw(srv, "command", "rules.save", {"ruleset_id": "showcase-path",
        "data_rules": [bad_path], "reason": "paths are an allowlist"}, "rules-path")) == "INVALID_INPUT"

    # ---- G views: the read models the AGH panel renders ----------------------------------
    trace = query("project.trace", {"root_ref": p["task"].to_dict(), "direction": "both", "max_depth": 4})["data"]
    assert trace["root"]["object_id"] == p["task"].object_id
    assert trace["node_count"] >= 2 and trace["edge_count"] >= 1 and isinstance(trace["truncated"], bool)

    coverage = query("requirements.coverage")["data"]
    assert coverage["denominator"] >= 1 and coverage["covered"] == coverage["denominator"]

    environment = query("environment.report", {"task_ref": p["task"].to_dict()})["data"]
    assert environment["data_state"] == "ok" and environment["facts"]
    for bucket in ("satisfied", "missing", "unknown", "too_old", "not_checked"):
        assert bucket in environment

    # The timeline is ordered by kind first (revision, head, event), newest first inside each
    # kind, so a view must page through it or re-sort; it is not one interleaved commit stream.
    seen_kinds, newest_by_kind, token, pages = set(), {}, None, 0
    while True:
        page = query("project.timeline", **({"page_token": token} if token else {}))
        pages += 1
        for entry in page["data"]["events"]:
            seq = int(entry["commit_seq"])
            assert seq <= newest_by_kind.get(entry["kind"], seq), "newest first within each kind"
            newest_by_kind[entry["kind"]] = seq
            seen_kinds.add(entry["kind"])
        token = page["next_page_token"]
        if not token:
            break
        assert pages < 50, "pagination must terminate"
    assert seen_kinds == {"revision", "head", "event"}
    only_attempts = query("project.timeline", {"object_type": "attempt"})["data"]["events"]
    assert only_attempts
    assert all(e["object_type"] == "attempt" for e in only_attempts if e["kind"] in {"revision", "head"})

    overview = query("project.overview")
    assert overview["freshness"]["state"] in {"fresh", "stale"} and overview["completeness"] in {
        "complete", "incomplete", "unknown"}
    assert overview["data"]["object_counts"].get("attempt", 0) >= 3

    # ---- A ledger: the frozen watermark still reads the old world and says it is stale ---
    historical = query("project.overview", as_of_seq=frozen_seq)
    # Same facts as when the watermark was frozen; only the completeness label differs, because
    # a lagging watermark is reported as incomplete instead of being passed off as current.
    assert without_completeness(historical["data"]) == without_completeness(frozen)
    assert frozen["completeness"] == "complete" and historical["data"]["completeness"] == "incomplete"
    assert historical["completeness"] == "incomplete"
    assert historical["freshness"]["projection_stale"] is True
    assert historical["data"]["object_counts"].get("attempt", 0) == 0
    events = query("events.read", {"after": {"commit_seq": "0", "event_index": 0}, "limit": 1000})["data"]
    assert events and [(e["commit_seq"], e["event_index"]) for e in events] == sorted(
        ((e["commit_seq"], e["event_index"]) for e in events), key=lambda k: (int(k[0]), k[1]))

    # ---- A ledger: facts and the watermark survive a restart -----------------------------
    final_seq = str(store.next_commit_seq() - 1)
    store.close()
    world["store"] = reopened = make_store(root, project_id=PROJECT)
    restarted = build_test_server(reopened)
    again = call(restarted, PROJECT, "project.overview", {}, query=True, as_of_seq=frozen_seq)
    assert without_completeness(again["data"]) == without_completeness(frozen)
    assert again["freshness"]["projection_stale"] is True
    assert call(restarted, PROJECT, "events.read", {"after": {"commit_seq": final_seq, "event_index": 999},
                                                    "limit": 100}, query=True)["data"] == []

    # ---- isolation: another project's selector is refused --------------------------------
    other = make_store(root, project_id="proj-other", store_id="store-other")
    try:
        denied = raw(restarted, "query", "project.overview", {})
        assert "error" not in denied
        wrong = decode_frame(restarted.handle_line(encode_frame({"jsonrpc": "2.0", "id": "r2", "method": "kernel.query",
            "params": {"protocol_version": "1.0.0", "invocation_context_id": "ctx1",
                       "selector": {"project_id": "proj-other"}, "query": "project.overview", "payload": {}}})))
        assert wrong["error"]["data"]["code"] == "SCOPE_MISMATCH"
    finally:
        other.close()


def test_module_tree_registry_is_a_tree_with_resolvable_relations():
    registry = json.loads((KERNEL_ROOT / "docs" / "modules" / "registry.json").read_text(encoding="utf-8"))
    nodes = {n["node_id"]: n for n in registry["nodes"]}
    assert len(nodes) == len(registry["nodes"]) == 23
    roots = [n for n in nodes.values() if n["navigation_parent"] is None]
    assert [r["node_id"] for r in roots] == ["K-ROOT"]
    for node in nodes.values():
        for key in ("depends_on", "related_to"):
            assert set(node[key]) <= set(nodes), (node["node_id"], key)
        if node["navigation_parent"] is not None:
            assert node["navigation_parent"] in nodes
        seen, cursor = set(), node["node_id"]
        while cursor is not None:  # navigation_parent must never loop
            assert cursor not in seen, f"navigation cycle at {cursor}"
            seen.add(cursor)
            cursor = nodes[cursor]["navigation_parent"]
    assert not any(n["conversation_refs"] for n in nodes.values()), "no conversation links were invented"


def test_skill_registry_keeps_scoring_unaveraged_and_untrusted_by_default():
    registry = json.loads((KERNEL_ROOT / "docs" / "records" / "skills" / "registry.json").read_text(encoding="utf-8"))
    assert registry["skills"]
    forbidden = {"average", "avg", "total_score", "overall_score", "user_score"}

    def keys(value):
        if isinstance(value, dict):
            for k, v in value.items():
                yield k
                yield from keys(v)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    assert not forbidden & set(keys(registry)), "skill scores are per-dimension observations, never averaged"
    for skill in registry["skills"]:
        current = [v for v in skill["versions"] if v["version"] == skill["current_version"]]
        assert len(current) == 1
        assert current[0]["validation_status"] != "validated" or current[0]["evidence_refs"]
