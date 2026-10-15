"""Demo stdio host for the AGH adapter (test mode, machine channel only).

Composes the shipped kernel root with the heat-inversion executor and checker,
seeds host-owned configuration, and serves newline-framed JSON-RPC on stdio.
Methods under "host." are host-owned observations, not kernel commands.
The human approval channel is deliberately absent from this process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
for entry in (ROOT / "src", TESTS):
    sys.path.insert(0, str(entry))

from project_kernel.application.environment_service import PythonEnvironmentProbe  # noqa: E402
from project_kernel.bootstrap import InvocationContextRegistry, build_server  # noqa: E402
from project_kernel.contracts import ALL_CAPABILITIES  # noqa: E402
from project_kernel.contracts.dto import ObjectRef  # noqa: E402
from project_kernel.data.store.store import Store  # noqa: E402
from project_kernel.evidence import ArtifactStorage, BundleExporter  # noqa: E402
from project_kernel.interfaces.rpc.framing import LineFramer, decode_frame, encode_frame  # noqa: E402

from p02_design.helpers import prepare_dispatch, seed  # noqa: E402
from p14_science_demo.science_checker import HeatCheckProvider  # noqa: E402
from p14_science_demo.science_executor import HeatInverseExecutor  # noqa: E402

PROJECT_ID = "agh-heat-demo"
HANDLE = "agh-machine-handle"
WORKER = Path(__file__).with_name("heat_worker.py")
STRATEGIES = {
    "s1": ["grid", "--step", "0.05"],
    "s2": ["golden", "--iters", "30"],
    "s3": ["stall", "--hang", "30"],
}


def rpc_result(rpc_id, result):
    return encode_frame({"jsonrpc": "2.0", "id": rpc_id, "result": result})


def rpc_error(rpc_id, code, message):
    return encode_frame({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}})


class DemoHost:
    def __init__(self, root: Path, poll_timeout: float):
        self.root = root
        self.store = Store.open_project(root / "demo.sqlite", PROJECT_ID, "agh-heat-store")
        self.storage = ArtifactStorage(root / "artifacts")
        exporter = BundleExporter(root / "exports", self.storage, allowed_sinks=("exports",))
        argv = {key: [sys.executable, "-I", str(WORKER), *args] for key, args in STRATEGIES.items()}
        self.executor = HeatInverseExecutor(self.store, argv, poll_timeout=poll_timeout)
        registry = InvocationContextRegistry(handle_factory=lambda: HANDLE)
        registry.mint("agh-agent", ALL_CAPABILITIES, project_id=PROJECT_ID)
        self.checker = HeatCheckProvider(self.store, self.storage)
        self.server = build_server(
            self.store, principal="agh-agent", contexts=registry, mode="test",
            executor=self.executor, artifact_root=root / "artifacts", bundle_exporter=exporter,
            environment_provider=PythonEnvironmentProbe(),
            check_provider=self.checker)

    def seed_demo(self) -> dict:
        def invoke(name, body, key):
            params = {"protocol_version": "1.0.0", "invocation_context_id": HANDLE,
                      "selector": {"project_id": PROJECT_ID}, "command": name, "payload": body,
                      "expected_heads": [], "idempotency_key": key}
            frame = encode_frame({"jsonrpc": "2.0", "id": "seed", "method": "kernel.command", "params": params})
            response = decode_frame(self.server.handle_line(frame))
            receipt = response["result"]["receipt"]
            if receipt["status"] == "rejected":
                raise RuntimeError(f"seed {name} rejected: {receipt}")
            return receipt

        state = prepare_dispatch(self.store, self.root / "work", strategies=tuple(STRATEGIES), invoke=invoke)
        target = seed(self.store, "delivery_target", "bundle", {"method": "bundle", "sink_id": "exports"})
        summary = {
            "project_id": PROJECT_ID, "context_handle": HANDLE,
            "task_ref": state["task"].to_dict(), "packet_ref": state["packet"].to_dict(),
            "acceptance_ref": state["acceptance"].to_dict(), "target_ref": target.to_dict(),
            "execution_roots": {key: ref.to_dict() for key, ref in state["roots"].items()},
        }
        (self.root / "demo-state.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def publish_candidate(self, params: dict) -> dict:
        attempt = ObjectRef.from_dict(params["attempt_ref"])
        payload = self.store.get_revision(attempt)["payload"]
        root_path = Path(self.store.get_revision(ObjectRef.from_dict(payload["execution_root_ref"]))["payload"]["path"])
        raw = (root_path / "result.json").read_bytes()
        artifact = self.storage.publish(self.storage.stage(raw, "application/json"), "application/json")
        oid = "cand-" + attempt.object_id
        ref = seed(self.store, "candidate_manifest", oid,
                   {"attempt_ref": attempt.to_dict(), "candidate_digest": hashlib.sha256(raw).hexdigest(),
                    "artifacts": [artifact.to_dict()]})
        # The solver's own claims, echoed for display only; the checker re-derives the verdict.
        data = json.loads(raw)
        summary = {key: data.get(key) for key in ("method", "alpha_fit", "elapsed_s")}
        return {"candidate_manifest_ref": ref.to_dict(), "summary": summary}

    def attempt_ref(self, params: dict) -> dict:
        """Current head revision of an attempt (selection needs the settled revision)."""
        attempt_id = str(params["attempt_id"])
        head = self.store.get_head("attempt", attempt_id, "current")
        if head is None:
            raise KeyError(f"attempt {attempt_id} not found")
        return {"attempt_ref": ObjectRef(PROJECT_ID, "attempt", attempt_id, head["revision_id"]).to_dict()}

    def last_check(self, _params: dict) -> dict:
        """Reason text of the most recent independent check run by this host."""
        return {"reason": self.checker.last_reason, "calls": self.checker.calls}

    def handle(self, frame: bytes) -> bytes:
        try:
            message = decode_frame(frame)
        except Exception as exc:
            return rpc_error(None, -32700, f"Parse error: {exc}")
        method = message.get("method")
        if isinstance(method, str) and method.startswith("host."):
            rpc_id = message.get("id")
            try:
                handlers = {"host.publish_candidate": self.publish_candidate,
                            "host.attempt_ref": self.attempt_ref, "host.last_check": self.last_check}
                if method in handlers:
                    return rpc_result(rpc_id, handlers[method](message.get("params", {})))
                return rpc_error(rpc_id, -32601, f"unknown host method {method}")
            except Exception as exc:
                return rpc_error(rpc_id, -32000, f"{type(exc).__name__}: {exc}")
        return self.server.handle_line(frame)

    def close(self):
        self.executor.close()
        self.store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--poll-timeout", type=float, default=3.0)
    args = parser.parse_args()
    root = args.root.resolve()
    allowed = (ROOT / ".validation-tmp", Path(tempfile.gettempdir()).resolve())
    if not any(root.is_relative_to(base) for base in allowed):
        parser.error("the demo host requires a root under .validation-tmp or the system temp directory")
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    host = DemoHost(root, args.poll_timeout)
    try:
        if not (root / "demo-state.json").exists():
            host.seed_demo()
        framer = LineFramer()
        while chunk := sys.stdin.buffer.read1(4096):
            for frame in framer.feed(chunk):
                sys.stdout.buffer.write(host.handle(frame))
                sys.stdout.buffer.flush()
    finally:
        host.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
