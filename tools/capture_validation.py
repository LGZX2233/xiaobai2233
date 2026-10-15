"""Capture a local validation command and its exit status without shell parsing."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TIME = timezone(timedelta(hours=8))


def _validation_fingerprints() -> dict[str, str]:
    paths = [ROOT / "pyproject.toml", ROOT / ".gitattributes"]
    for directory in ("src", "tests", "bridge", "contracts", "tools", "fixtures"):
        paths.extend(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and not any(part.endswith(".egg-info") for part in path.parts)
                     and path.suffix not in {".pyc", ".pyo"})
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def main() -> int:
    """Run an explicit command in the kernel directory and retain its output.

    Returns the child exit code. Existing captures are never overwritten; move
    failed evidence into a separate attempt directory before another run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not re.fullmatch(r"[a-z0-9-]+", args.name):
        parser.error("provide a command and a lowercase capture name")
    evidence = (ROOT / args.evidence_dir).resolve()
    if not evidence.is_relative_to(ROOT):
        parser.error("evidence directory must remain under the kernel root")
    evidence.mkdir(parents=True, exist_ok=True)
    output_path = evidence / f"{args.name}-output.txt"
    result_path = evidence / f"{args.name}-result.json"
    if output_path.exists() or result_path.exists():
        parser.error("capture already exists; preserve it before another run")
    started = datetime.now(LOCAL_TIME).isoformat()
    fingerprints = _validation_fingerprints()
    completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
    final_fingerprints = _validation_fingerprints()
    with output_path.open("xb") as capture:
        capture.write(completed.stdout)
    result = {
        "mode": "test",
        "cwd": str(ROOT),
        "command": command,
        "started_at": started,
        "finished_at": datetime.now(LOCAL_TIME).isoformat(),
        "exit_code": completed.returncode,
        "output": output_path.relative_to(ROOT).as_posix(),
        "output_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "validation_files_sha256": fingerprints,
        "validation_files_unchanged": fingerprints == final_fingerprints,
    }
    with result_path.open("x", encoding="utf-8") as capture:
        capture.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(completed.stdout.decode("utf-8", errors="replace"))
    print(json.dumps({"capture": str(result_path), "exit_code": completed.returncode}))
    return completed.returncode or (0 if fingerprints == final_fingerprints else 1)


if __name__ == "__main__":
    raise SystemExit(main())
