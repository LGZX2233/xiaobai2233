"""The AGH demo host over real stdio pipes: seed, run a strategy, publish, verify."""
import json
import subprocess
import sys
from pathlib import Path

HOST = Path(__file__).with_name("agh_host.py")


class Pipe:
    def __init__(self, root: Path):
        self.proc = subprocess.Popen(
            [sys.executable, "-I", "-X", "utf8", str(HOST), "--root", str(root), "--poll-timeout", "20"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.n = 0
        self.state = json.loads((root / "demo-state.json").read_text(encoding="utf-8")) \
            if (root / "demo-state.json").exists() else None
        self.root = root

    def send(self, method, params):
        self.n += 1
        frame = {"jsonrpc": "2.0", "id": f"t{self.n}", "method": method, "params": params}
        self.proc.stdin.write((json.dumps(frame) + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def command(self, name, payload, key):
        if self.state is None:
            self.state = json.loads((self.root / "demo-state.json").read_text(encoding="utf-8"))
        return self.send("kernel.command", {
            "protocol_version": "1.0.0", "invocation_context_id": self.state["context_handle"],
            "selector": {"project_id": self.state["project_id"]}, "command": name,
            "payload": payload, "expected_heads": [], "idempotency_key": key})

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=20)


def test_host_runs_golden_strategy_and_checker_over_stdio(tmp_path):
    root = tmp_path / "agh"
    pipe = Pipe(root)
    try:
        init = pipe.send("kernel.initialize", {"client_id": "t", "supported_protocol_versions": ["1.0.0"]})
        assert init["result"]["mode"] == "test"
        state = pipe.state = json.loads((root / "demo-state.json").read_text(encoding="utf-8"))
        started = pipe.command("attempt.start", {
            "packet_ref": state["packet_ref"], "strategy_id": "s2",
            "execution_root_ref": state["execution_roots"]["s2"]}, "start-s2")
        receipt = started["result"]["receipt"]
        assert receipt["status"] != "rejected", receipt
        attempt = receipt["object_refs"][0]
        published = pipe.send("host.publish_candidate", {"attempt_ref": attempt})
        candidate = published["result"]["candidate_manifest_ref"]
        verified = pipe.command("verification.run", {
            "attempt_ref": attempt, "candidate_manifest_ref": candidate,
            "acceptance_refs": [state["acceptance_ref"]]}, "verify-s2")
        assert verified["result"]["receipt"]["status"] != "rejected", verified
        report = pipe.send("kernel.query", {
            "protocol_version": "1.0.0", "invocation_context_id": state["context_handle"],
            "selector": {"project_id": state["project_id"]}, "query": "project.overview", "payload": {}})
        assert "error" not in report, report
    finally:
        pipe.close()
