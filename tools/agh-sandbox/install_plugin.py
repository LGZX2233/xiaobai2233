#!/usr/bin/env python3
"""Install the Project Kernel AGH plugin non-interactively (disable/remove -> add -> trust -> enable).

`agh package add` asks "Install <id>@<version> (<integrity>)? [y/N]" only when stdin and stdout are
TTYs (packages/cli/src/bin.ts confirmPackageInstall), so the add step runs under a pseudo terminal
and a person-equivalent "y" is typed. trust needs the integrity and capability hash that the
daemon records for the preview in <AGH_HOME>/data/daemon/package-operations/operations.json.

Usage (all paths are arguments or environment variables; nothing here contains a credential):
  python3 install_plugin.py --cwd /tmp/kn_agh/kernel_next [--source file:./adapters/agh-plugin]
Environment: AGH_NODE (node 24 binary), AGH_JS (agnes.mjs), AGH_HOME, AGNES_PROFILE.
"""
import argparse
import json
import os
import pty
import select
import subprocess
import sys
import time

PACKAGE_ID = "@project-kernel/agh-plugin"


def agh_env(args):
    env = dict(os.environ)
    env["AGH_HOME"] = args.home
    env["AGNES_PROFILE"] = args.profile
    env["PATH"] = os.path.dirname(args.node) + os.pathsep + env.get("PATH", "")
    return env


def run(args, argv, label):
    """Run one agh command without a terminal and echo its output."""
    cmd = [args.node, args.agh_js, "package", "--profile", args.profile, *argv]
    proc = subprocess.run(cmd, cwd=args.cwd, env=agh_env(args), capture_output=True, text=True, timeout=120)
    out = (proc.stdout + proc.stderr).strip()
    print(f"$ agh package {' '.join(argv)}  -> exit {proc.returncode}")
    if out:
        print(out)
    return proc.returncode, out


def run_pty(args, argv, answer, prompt_marker="[y/N] "):
    """Run an agh command under a pty and type `answer` when the confirmation prompt appears."""
    cmd = [args.node, args.agh_js, "package", "--profile", args.profile, *argv]
    master, slave = os.openpty()
    proc = subprocess.Popen(cmd, cwd=args.cwd, env=agh_env(args), stdin=slave, stdout=slave, stderr=slave,
                            close_fds=True, start_new_session=True)
    os.close(slave)
    buf = b""
    answered = False
    deadline = time.time() + 120
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.5)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if not answered and prompt_marker.encode() in buf:
                os.write(master, (answer + "\r").encode())
                answered = True
        elif proc.poll() is not None:
            break
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    os.close(master)
    text = buf.decode("utf-8", "replace").replace("\r\n", "\n").strip()
    print(f"$ agh package {' '.join(argv)}  (pty, typed {answer!r} at the prompt) -> exit {proc.returncode}")
    print(text)
    return proc.returncode, text


def latest_preview(args):
    path = os.path.join(args.home, "data", "daemon", "package-operations", "operations.json")
    data = json.load(open(path, encoding="utf-8"))
    found = None
    for entry in data.get("operations", []):
        preview = (entry.get("operation") or {}).get("preview") or {}
        if preview.get("id") == PACKAGE_ID and preview.get("integrity") and preview.get("capabilityHash"):
            found = preview
    return found


def installed(status_text):
    return any(line.startswith(PACKAGE_ID + "@") for line in status_text.splitlines())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cwd", required=True, help="kernel_next checkout the relative --source is resolved from")
    ap.add_argument("--source", default="file:./adapters/agh-plugin")
    ap.add_argument("--node", default=os.environ.get("AGH_NODE", "/tmp/node-v24.22.0-linux-x64/bin/node"))
    ap.add_argument("--agh-js", default=os.environ.get("AGH_JS", "/tmp/aghrt/agnes.mjs"))
    ap.add_argument("--home", default=os.environ.get("AGH_HOME", "/tmp/agh_home"))
    ap.add_argument("--profile", default=os.environ.get("AGNES_PROFILE", "local-dev"))
    args = ap.parse_args()

    _, status = run(args, ["status"], "status")
    if installed(status):
        run(args, ["disable", PACKAGE_ID], "disable")
        run(args, ["remove", PACKAGE_ID], "remove")
    rc, _ = run_pty(args, ["add", args.source], "y")
    preview = latest_preview(args)
    if rc != 0 or not preview:
        print("FAILED: add did not complete or no preview record found", file=sys.stderr)
        return 2
    print(f"integrity={preview['integrity']}\ncapabilityHash={preview['capabilityHash']}")
    run(args, ["trust", PACKAGE_ID, preview["integrity"], preview["capabilityHash"]], "trust")
    run(args, ["enable", PACKAGE_ID], "enable")
    time.sleep(2)
    _, status = run(args, ["status"], "status")
    ok = any(line.startswith(PACKAGE_ID + "@") and "actual=running" in line and "trusted=true" in line
             for line in status.splitlines())
    print("RESULT:", "plugin installed, trusted, running" if ok else "plugin NOT running")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
