"""Public-entry G2 stream evidence and instrumented dual-project test workflow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from project_kernel.contracts.digest import compute_bundle_digest
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.protocol import ProtocolServer
from p01_store.helpers import make_store
from p13_integration.auth_helpers import build_test_server
from p13_integration import test_closed_loop as workflow

ROOT = Path(__file__).resolve().parents[2]


def test_ac37_real_stdio_composition_root(tmp_path, request):
    params = {"protocol_version": "1.0.0", "invocation_context_id": "test-protocol-handle",
              "selector": {"project_id": "protocol-project"}, "command": "task.create",
              "payload": {"title": "stream task", "goal": "isolated framing",
                          "requirement_refs": [], "mode": "test"},
              "expected_heads": [], "idempotency_key": "stream-task"}
    command = encode_frame({"jsonrpc": "2.0", "id": "task", "method": "kernel.command", "params": params})
    initialize = encode_frame({"jsonrpc": "2.0", "id": "init", "method": "kernel.initialize",
                               "params": {"client_id": "stream-test", "supported_protocol_versions": ["1.0.0"]}})
    bad = [b'{"a":1,"\\u0061":2}\n', b'{"a":"\xff"}\n',
           b'{"values":[1e999]}\n', b"x" * (1024 * 1024 + 1)]
    process = subprocess.run([sys.executable, "-X", "utf8", "-B",
                              str(Path(__file__).with_name("stdio_test_host.py")), "--root", str(tmp_path)],
                             input=initialize + command + b"".join(bad), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=ROOT, timeout=30, check=False)
    assert process.returncode == 0, process.stderr.decode("utf-8", errors="replace")
    responses = [decode_frame(line) for line in process.stdout.splitlines()]
    assert responses[0]["result"]["schema_bundle_digest"] == compute_bundle_digest()
    assert responses[1]["result"]["receipt"]["status"] == "committed"
    assert [row["error"]["code"] for row in responses[2:]] == [-32700, -32700, -32700, -32600]
    assert b"kernel.command" in process.stderr
    assert b"test-protocol-handle" not in process.stderr
    (tmp_path / "protocol-evidence.json").write_text(json.dumps({
        "nodeid": request.node.nodeid, "mode": "test", "root": str(tmp_path), "contract_digest": compute_bundle_digest(),
        "requests": [json.loads(initialize), json.loads(command)], "invalid_inputs_hex": [b.hex() if len(b) < 100 else "oversize:1048577" for b in bad],
        "responses": responses, "stderr": process.stderr.decode("utf-8"),
        "stdout_sha256": hashlib.sha256(process.stdout).hexdigest()}, indent=2) + "\n", encoding="utf-8")


def test_ac43_ac45_instrumented_public_workflow(tmp_path, monkeypatch, request):
    traces = []
    seed_refs = []
    handle = ProtocolServer.handle_line
    seed = workflow.seed

    def record(self, line):
        response = handle(self, line)
        traces.append({"entry": "human" if "approval.decide" in self.supported_commands else "machine",
                       "request": decode_frame(line), "response": decode_frame(response)})
        return response

    def record_seed(store, kind, oid, payload):
        ref = seed(store, kind, oid, payload)
        seed_refs.append({"ref": ref.to_dict(), "payload": payload,
                          "digest": store.get_revision(ref)["digest"]})
        return ref

    monkeypatch.setattr(ProtocolServer, "handle_line", record)
    monkeypatch.setattr(workflow, "seed", record_seed)
    workflow.test_dual_project_workflow_delivery_archive_and_offline_restore(tmp_path, monkeypatch)
    scenario = json.loads((tmp_path / "scenario-evidence.json").read_text(encoding="utf-8"))
    assert scenario["provider_calls"] == 3 and scenario["archive_repaired"]
    inventory = []
    for path in sorted(tmp_path.rglob("*")):
        if path.is_file():
            assert path.resolve().is_relative_to(tmp_path.resolve())
            inventory.append({"path": path.relative_to(tmp_path).as_posix(), "size": path.stat().st_size,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "runtime_database": ".sqlite" in path.name})
    assert any(row["path"].startswith("A/exports/") and row["path"].endswith("manifest.json") for row in inventory)
    assert any(row["path"] == "A/s1/output.txt" for row in inventory)
    assert any(row["path"] == "A/s2/output.txt" for row in inventory)
    assert any(row["path"] == "B/proj-b.sqlite" for row in inventory)
    (tmp_path / "closed-loop-evidence.json").write_text(json.dumps({
        "nodeid": request.node.nodeid, "mode": "test", "sandbox_guarantee": "directory_only", "root": str(tmp_path),
        "contract_digest": compute_bundle_digest(), "host_owned_seed_refs": seed_refs,
        "trace": traces, "scenario": scenario, "inventory": inventory}, indent=2) + "\n", encoding="utf-8")


def test_ac38_public_receipt_survives_reopen_and_missing_is_unknown(tmp_path, request):
    store = make_store(tmp_path)
    trace = []
    task = {"title": "lost reply", "goal": "durable same-key recovery", "requirement_refs": [], "mode": "test"}

    def rpc(server, name, payload, query=False):
        params = {"protocol_version": "1.0.0", "invocation_context_id": "ctx1",
                  "selector": {"project_id": "proj-a"}, "payload": payload}
        params.update({"query": name} if query else {
            "command": name, "idempotency_key": "original", "expected_heads": []})
        msg = {"jsonrpc": "2.0", "id": str(len(trace)), "method": "kernel.query" if query else "kernel.command", "params": params}
        response = decode_frame(server.handle_line(encode_frame(msg)))
        trace.append({"request": msg, "response": response})
        assert "error" not in response, response
        return response["result"]

    try:
        original = rpc(build_test_server(store), "task.create", task)["receipt"]
        live_files = [{"path": path.relative_to(tmp_path).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in tmp_path.iterdir() if path.is_file()]
        assert any(path["path"].endswith("-wal") for path in live_files)
        assert any(path["path"].endswith("-shm") for path in live_files)
        store.close()
        store = make_store(tmp_path)
        restarted = build_test_server(store)
        recovered = rpc(restarted, "command.receipt", {
            "receipt_domain": "project", "idempotency_key": "original"}, True)["data"]["receipt"]
        assert recovered == original
        assert rpc(restarted, "task.create", task)["receipt"] == original
        unknown = rpc(restarted, "command.receipt", {
            "receipt_domain": "project", "idempotency_key": "never-issued"}, True)["data"]
        assert unknown is None
        overview = rpc(restarted, "project.overview", {}, True)
        assert overview["data"]["object_counts"]["task"] == 1
        (tmp_path / "receipt-reconnect-evidence.json").write_text(json.dumps({
            "nodeid": request.node.nodeid, "mode": "test", "root": str(tmp_path), "contract_digest": compute_bundle_digest(),
            "trace": trace, "live_files": live_files, "recovered": recovered,
            "missing_receipt": unknown, "overview": overview}, indent=2) + "\n", encoding="utf-8")
    finally:
        store.close()
