"""Validation captures must describe passing commands on unchanged files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy

import pytest

CHECK_CAPTURE = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "tools" / "verify_g2_evidence.py"))["_check_capture"]


def _capture(root):
    source = root / "source.py"
    source.write_bytes(b"value = 1\n")
    output = root / "output.txt"
    output.write_bytes(b"passed\n")
    capture = {
        "exit_code": 0, "output": "output.txt",
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "validation_files_sha256": {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()},
        "validation_files_unchanged": True,
    }
    (root / "capture.json").write_text(json.dumps(capture), encoding="utf-8")
    return capture


def test_stable_successful_capture_is_accepted(tmp_path):
    _capture(tmp_path)
    assert CHECK_CAPTURE(tmp_path, "capture.json", require_fingerprints=True) == []


@pytest.mark.parametrize("damage,reason", [
    ("exit", "failed capture"),
    ("output", "capture output hash changed"),
    ("source", "capture input hash changed"),
    ("missing_fingerprints", "capture has no stable input fingerprints"),
    ("unstable", "capture has no stable input fingerprints"),
    ("outside_output", "missing or outside root capture output"),
    ("outside_input", "missing or outside root capture input"),
])
def test_invalid_capture_cannot_verify_current_code(tmp_path, damage, reason):
    capture = _capture(tmp_path)
    if damage == "exit":
        capture["exit_code"] = 1
    elif damage == "output":
        (tmp_path / "output.txt").write_bytes(b"different\n")
    elif damage == "source":
        (tmp_path / "source.py").write_bytes(b"value = 2\n")
    elif damage == "missing_fingerprints":
        capture.pop("validation_files_sha256")
    elif damage == "unstable":
        capture["validation_files_unchanged"] = False
    elif damage == "outside_output":
        capture["output"] = "../output.txt"
    elif damage == "outside_input":
        capture["validation_files_sha256"] = {"../source.py": "a" * 64}
    (tmp_path / "capture.json").write_text(json.dumps(capture), encoding="utf-8")
    assert any(problem.startswith(reason) for problem in
               CHECK_CAPTURE(tmp_path, "capture.json", require_fingerprints=True))
