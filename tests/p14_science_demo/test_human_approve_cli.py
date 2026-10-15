"""Human approval CLI decides while the AGH demo host is still running on the same store."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from p14_science_demo.test_agh_host_stdio import Pipe

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "tools" / "pk_human_approve.py"


def load_cli():
    spec = importlib.util.spec_from_file_location("pk_human_approve", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ok(response):
    assert "error" not in response, response
    receipt = response["result"]["receipt"]
    assert receipt["status"] != "rejected", receipt
    return receipt


def request_delivery(pipe, root):
    """Drive the host (machine channel) up to a pending approval for strategy s2."""
    pipe.send("kernel.initialize", {"client_id": "t", "supported_protocol_versions": ["1.0.0"]})
    state = pipe.state = json.loads((root / "demo-state.json").read_text(encoding="utf-8"))
    started = ok(pipe.command("attempt.start", {"packet_ref": state["packet_ref"], "strategy_id": "s2",
                                                "execution_root_ref": state["execution_roots"]["s2"]}, "s2"))
    attempt_id = started["object_refs"][0]["object_id"]
    attempt = pipe.send("host.attempt_ref", {"attempt_id": attempt_id})["result"]["attempt_ref"]
    candidate = pipe.send("host.publish_candidate", {"attempt_ref": attempt})["result"]["candidate_manifest_ref"]
    ok(pipe.command("verification.run", {"attempt_ref": attempt, "candidate_manifest_ref": candidate,
                                         "acceptance_refs": [state["acceptance_ref"]]}, "verify"))
    selection = ok(pipe.command("attempt.select", {"attempt_ref": attempt, "comparison_refs": [attempt],
                                                   "purpose": "delivery", "reason": "passes"}, "select"))
    requested = ok(pipe.command("delivery.request", {"selection_ref": selection["object_refs"][0],
                                                     "candidate_ref": candidate,
                                                     "target_ref": state["target_ref"]}, "request"))
    return next(r["object_id"] for r in requested["object_refs"] if r["object_type"] == "approval")


def pending(cli, root):
    store = cli.open_store(root)
    try:
        return cli.pending_approvals(store)
    finally:
        store.close()


def test_human_cli_decides_concurrently_with_running_host(tmp_path):
    cli = load_cli()
    root = tmp_path / "agh"
    pipe = Pipe(root)
    try:
        approval_id = request_delivery(pipe, root)
        assert pipe.proc.poll() is None, "the AGH host process must still be alive"

        # The host process still holds its store open; the CLI opens the same file concurrently.
        entries = pending(cli, root)
        assert [p["approval_id"] for p in entries] == [approval_id]
        entry = entries[0]
        assert entry["strategy_id"] == "s2"
        assert abs(entry["alpha_fit"] - 0.37286) < 1e-4

        digest = entry["snapshot_digest"]
        for bad in ("00000000", digest[:7], "zzzzzzzz", "", digest[:8].upper().replace(digest[0].upper(), "G", 1)):
            with pytest.raises(cli.ApprovalError):
                cli.decide(root, approval_id, bad, "approved", "wrong digest")
        with pytest.raises(cli.ApprovalError):
            cli.decide(root, approval_id, digest[:8], "approved", " ")
        with pytest.raises(cli.ApprovalError):
            cli.decide(root, approval_id, digest[:8], "maybe", "x")
        assert [p["approval_id"] for p in pending(cli, root)] == [approval_id], "refusals decided nothing"

        # Applying before a person decided must still be refused by the kernel.
        early = pipe.command("delivery.apply", {"approval_id": approval_id, "snapshot_digest": digest}, "apply-early")
        assert "error" in early or early["result"]["receipt"]["status"] == "rejected", early

        result = cli.decide(root, approval_id, digest[:8], "approved", "checked digest")
        assert result["approval_status"] == "approved"
        assert pipe.proc.poll() is None, "the host kept running during the human decision"
        assert pending(cli, root) == []

        applied = ok(pipe.command("delivery.apply", {"approval_id": approval_id, "snapshot_digest": digest}, "apply"))
        assert applied["operation_id"]
    finally:
        pipe.close()


def test_human_cli_rejection_blocks_delivery(tmp_path):
    cli = load_cli()
    root = tmp_path / "agh"
    pipe = Pipe(root)
    try:
        approval_id = request_delivery(pipe, root)
        entry = pending(cli, root)[0]
        digest = entry["snapshot_digest"]
        with pytest.raises(cli.ApprovalError):
            cli.decide(root, approval_id, digest[:8], "rejected", "")
        result = cli.decide(root, approval_id, digest[:8], "rejected", "alpha 与解析解不符")
        assert result["approval_status"] == "rejected"
        refused = pipe.command("delivery.apply", {"approval_id": approval_id, "snapshot_digest": digest}, "apply")
        assert "error" in refused or refused["result"]["receipt"]["status"] == "rejected", refused
    finally:
        pipe.close()


def test_human_cli_refuses_without_a_terminal(tmp_path):
    (tmp_path / "demo.sqlite").write_bytes(b"")
    proc = subprocess.run([sys.executable, "-I", str(CLI), "--root", str(tmp_path)],
                          stdin=subprocess.PIPE, capture_output=True, timeout=60)
    assert proc.returncode == 2
    assert "TTY" in proc.stderr.decode("utf-8")


def test_human_cli_has_no_test_imports_and_states_its_limit():
    import ast

    source = CLI.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module}
    imported |= {alias.name.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.Import) for alias in node.names}
    assert imported <= {"__future__", "argparse", "json", "re", "sys", "tempfile", "pathlib", "typing",
                        "project_kernel"}, imported
    assert "not a security boundary" in " ".join(ast.get_docstring(tree).split())


@pytest.mark.skipif(os.name != "posix", reason="needs a pseudo terminal")
def test_human_cli_interactive_session_in_a_pty(tmp_path):
    """A person at a terminal: type a wrong prefix (nothing happens), then the right one."""
    import pty
    import select

    cli = load_cli()
    root = tmp_path / "agh"
    pipe = Pipe(root)
    try:
        approval_id = request_delivery(pipe, root)
        digest = pending(cli, root)[0]["snapshot_digest"]
        master, slave = pty.openpty()
        proc = subprocess.Popen([sys.executable, "-I", "-X", "utf8", str(CLI), "--root", str(root)],
                                stdin=slave, stdout=slave, stderr=slave, close_fds=True, start_new_session=True)
        os.close(slave)
        seen = b""

        def feed_when(marker, text, timeout=60):
            nonlocal seen
            deadline = time.time() + timeout
            while marker.encode() not in seen and time.time() < deadline:
                ready, _, _ = select.select([master], [], [], 0.5)
                if ready:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    seen += chunk
            assert marker.encode() in seen, seen.decode("utf-8", "replace")
            seen = seen.split(marker.encode(), 1)[1]
            os.write(master, (text + "\n").encode())

        feed_when("直接回车取消", "deadbeef")        # wrong prefix
        feed_when("批准理由", "")                    # default reason; kernel side must refuse the prefix
        proc.wait(timeout=60)
        assert proc.returncode == 1
        assert [p["approval_id"] for p in pending(cli, root)] == [approval_id]
        os.close(master)

        master, slave = pty.openpty()
        proc = subprocess.Popen([sys.executable, "-I", "-X", "utf8", str(CLI), "--root", str(root)],
                                stdin=slave, stdout=slave, stderr=slave, close_fds=True, start_new_session=True)
        os.close(slave)
        seen = b""
        feed_when("直接回车取消", digest[:8])
        feed_when("批准理由", "pty test reason")
        proc.wait(timeout=60)
        os.close(master)
        assert proc.returncode == 0
        assert pending(cli, root) == []
    finally:
        pipe.close()
