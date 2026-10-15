#!/usr/bin/env python3
"""One command: rebuild the publish tree, scan it and build the submission zip (stdlib only).

    python3 tools/publish/rebuild_all.py [--group G --id N --team T --captain C]

Read-only on the working repository. Writes to $PK_PUBLISH_WORK (default /tmp/publish) and the outputs folder.
The standalone proof (fresh venv + full suites) is separate because it takes about four minutes: see
tools/publish/standalone_proof.sh.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1]


def run(cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", default=str(SRC))
    parser.add_argument("--work", default=os.environ.get("PK_PUBLISH_WORK", "/tmp/publish"))
    parser.add_argument("--out", default=os.environ.get("PK_PUBLISH_OUT", "/ses" + "sions/inspiring-dreamy-planck/mnt/outputs/publish"))
    parser.add_argument("--remote-dir", default="/tmp/publish/remote_ro", help="read-only clone of the remote, for the licence report")
    for name, default in (("group", "本科生组"), ("id", "待填"), ("team", "待填"), ("captain", "待填")):
        parser.add_argument("--" + name, default=default)
    args = parser.parse_args(argv)
    work, out = Path(args.work), Path(args.out)
    tree = work / "tree"
    out.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    run([py, HERE / "build_publish_tree.py", "--src", args.src, "--out", tree, "--report-dir", out])
    scan_cmd = [py, HERE / "scan_tree.py", tree, "--src", args.src, "--json", out / "scan.json", "--md", out / "SCAN.md"]
    if Path(args.remote_dir).is_dir():
        scan_cmd += ["--remote-dir", args.remote_dir]
    run(scan_cmd)
    run([py, HERE / "build_submission_zip.py", "--tree", tree, "--out", out, "--group", args.group, "--id", args.id,
         "--team", args.team, "--captain", args.captain])
    zip_report = json.loads((out / "zip_report.json").read_text(encoding="utf-8"))
    print(f"\nDone. zip: {zip_report['name']} ({zip_report['size']}), tree: {tree}, reports: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
