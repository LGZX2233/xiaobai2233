"""Science demo: heat-conduction parameter inversion through the kernel's public RPC entry.

normal   : coarse grid fails acceptance, refined grid and golden-section pass, human approves
boundary : fabricated result and machine-side approval are both rejected
failure  : a stalled solver settles as unknown and is never relaunched
"""
import hashlib
import json
import sys
from pathlib import Path

from project_kernel.contracts.dto import ArtifactRef, ObjectRef
from project_kernel.application.environment_service import PythonEnvironmentProbe
from project_kernel.evidence import ArtifactStorage, BundleExporter
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, seed
from p13_integration.auth_helpers import build_test_server
from p13_integration.test_closed_loop import call, latest
from p14_science_demo.science_checker import HeatCheckProvider
from p14_science_demo.science_executor import HeatInverseExecutor

WORKER = str(Path(__file__).with_name("heat_worker.py"))


def argv(*args):
    return [sys.executable, "-I", WORKER, *args]


def publish_candidate(store, storage, attempt, result_path: Path, oid: str, raw: bytes | None = None):
    raw = result_path.read_bytes() if raw is None else raw
    artifact = storage.publish(storage.stage(raw, "application/json"), "application/json")
    return seed(store, "candidate_manifest", oid,
                {"attempt_ref": attempt.to_dict(), "candidate_digest": hashlib.sha256(raw).hexdigest(),
                 "artifacts": [artifact.to_dict()]})


def test_heat_inversion_normal_boundary_failure(tmp_path):
    root = tmp_path / "sci"
    root.mkdir()
    store = make_store(root, project_id="proj-sci")
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
    invoke = lambda name, body, key: call(srv, "proj-sci", name, body, key)
    try:
        p = prepare_dispatch(store, root, strategies=("s1", "s2", "s3"), invoke=invoke)

        def start(strategy, key):
            data = {"packet_ref": p["packet"].to_dict(), "strategy_id": strategy,
                    "execution_root_ref": p["roots"][strategy].to_dict()}
            receipt = invoke("attempt.start", data, key)
            return latest(store, "attempt", receipt["operation_id"])

        def verify(attempt, candidate, key):
            receipt = invoke("verification.run", {"attempt_ref": attempt.to_dict(),
                "candidate_manifest_ref": candidate.to_dict(),
                "acceptance_refs": [p["acceptance"].to_dict()]}, key)
            return store.get_revision(ObjectRef.from_dict(receipt["object_refs"][0]))["payload"]

        # failure sample: the stalled solver settles as unknown, no relaunch
        stalled = start("s3", "stall")
        assert store.get_revision(stalled)["payload"]["status"] == "unknown"
        launches_after_stall = executor.launches

        # normal sample 1: coarse grid completes but misses the acceptance tolerance
        coarse = start("s1", "coarse")
        assert store.get_revision(coarse)["payload"]["status"] == "completed"
        coarse_cand = publish_candidate(store, storage, coarse, root / "s1" / "result.json", "cand-coarse")
        assert verify(coarse, coarse_cand, "verify-coarse")["passed"] is False

        # normal sample 2: golden-section strategy passes
        golden = start("s2", "golden")
        golden_cand = publish_candidate(store, storage, golden, root / "s2" / "result.json", "cand-golden")
        assert verify(golden, golden_cand, "verify-golden")["passed"] is True

        # boundary sample: a fabricated fit with the real readings is rejected
        forged = json.loads((root / "s2" / "result.json").read_text(encoding="utf-8"))
        forged["alpha_fit"] = 0.9
        forged_cand = publish_candidate(store, storage, golden, None, "cand-forged",
                                        raw=json.dumps(forged).encode())
        assert verify(golden, forged_cand, "verify-forged")["passed"] is False

        selection = invoke("attempt.select", {"attempt_ref": golden.to_dict(),
            "comparison_refs": [stalled.to_dict(), coarse.to_dict(), golden.to_dict()],
            "purpose": "delivery", "reason": "golden-section meets tolerance; coarse grid does not"},
            "select")["object_refs"][0]
        target = seed(store, "delivery_target", "bundle", {"method": "bundle", "sink_id": "exports"})
        request = invoke("delivery.request", {"selection_ref": selection,
            "candidate_ref": golden_cand.to_dict(), "target_ref": target.to_dict()}, "request")
        approval = store.get_revision(ObjectRef.from_dict(request["object_refs"][0]))["payload"]
        decide = {"approval_id": approval["approval_id"], "snapshot_digest": approval["snapshot_digest"],
                  "decision": "approved", "reason": "reviewed fit against closed form"}
        refused = decode_frame(srv.handle_line(encode_frame({"jsonrpc": "2.0", "id": "x",
            "method": "kernel.command", "params": {"protocol_version": "1.0.0",
            "invocation_context_id": "ctx1", "selector": {"project_id": "proj-sci"},
            "command": "approval.decide", "payload": decide, "expected_heads": [],
            "idempotency_key": "machine-approve"}})))
        assert refused["error"]["data"]["code"] == "UNSUPPORTED_COMMAND"
        call(human, "proj-sci", "approval.decide", decide, "approve")

        applied = invoke("delivery.apply", {"approval_id": approval["approval_id"],
            "snapshot_digest": approval["snapshot_digest"]}, "apply")
        op = call(srv, "proj-sci", "operation.status", {"operation_id": applied["operation_id"]}, query=True)["data"]
        assert op["status"] == "applied"
        assert executor.launches == launches_after_stall + 2
    finally:
        executor.close()
        store.close()
