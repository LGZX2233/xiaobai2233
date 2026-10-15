#!/usr/bin/env python3
"""Add a model provider account to a local AGH daemon without ever printing the API key.

It drives the official `agh config` wizard (packages/cli/src/config-wizard.ts) through pipes: the
wizard is line oriented when stdin is not a TTY, so this script answers its prompts in order. The key
is read from a file at run time, written only to the wizard's stdin, and replaced by [key] in
everything this script prints or logs. Nothing is stored by this script; the daemon keeps the
credential in <AGH_HOME>/secrets/<provider>/default (mode 0600).

Usage:
  python3 configure_provider.py --provider deepseek --model deepseek-flash \
      --key-file /tmp/deepseek_key --account-name "DeepSeek (flash)" [--default]
Environment: AGH_NODE (node 24), AGH_JS (agnes.mjs), AGH_HOME, AGNES_PROFILE.
"""
import argparse
import os
import re
import select
import subprocess
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", required=True, help="provider id shown by the wizard, e.g. deepseek or agnes-ai")
    ap.add_argument("--model", required=True, help="model id to select from the provider's verified list")
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--account-name", required=True)
    ap.add_argument("--base-url", default="", help="leave empty to use the provider default")
    ap.add_argument("--cwd", default="/tmp")
    ap.add_argument("--node", default=os.environ.get("AGH_NODE", "/tmp/node-v24.22.0-linux-x64/bin/node"))
    ap.add_argument("--agh-js", default=os.environ.get("AGH_JS", "/tmp/aghrt/agnes.mjs"))
    ap.add_argument("--home", default=os.environ.get("AGH_HOME", "/tmp/agh_home"))
    ap.add_argument("--profile", default=os.environ.get("AGNES_PROFILE", "local-dev"))
    ap.add_argument("--transcript", help="optional file for the masked wizard transcript")
    args = ap.parse_args()

    key = open(args.key_file, encoding="utf-8").read().strip()
    if not key:
        print("empty key file", file=sys.stderr)
        return 2
    env = dict(os.environ, AGH_HOME=args.home, AGNES_PROFILE=args.profile)
    env["PATH"] = os.path.dirname(args.node) + os.pathsep + env.get("PATH", "")
    proc = subprocess.Popen([args.node, args.agh_js, "config", "--profile", args.profile], cwd=args.cwd, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    seen = ""
    log = []
    answered = set()

    def mask(text):
        return text.replace(key, "[key]")

    def send(prompt_id, text, shown=None):
        proc.stdin.write((text + "\n").encode())
        proc.stdin.flush()
        answered.add(prompt_id)
        log.append(f"  >> {shown if shown is not None else mask(text)}")

    fd_err, fd_out = proc.stderr.fileno(), proc.stdout.fileno()
    deadline = time.time() + 120
    consumed = 0
    while time.time() < deadline:
        ready, _, _ = select.select([fd_err, fd_out], [], [], 0.5)
        for fd in ready:
            chunk = os.read(fd, 4096)
            if chunk:
                text = mask(chunk.decode("utf-8", "replace"))
                seen += text
                log.append(text.rstrip("\n"))
        pending = seen[consumed:]
        if (m := re.search(r"Account \[0 = add\]: $", pending)):
            send("account", "0"); consumed = len(seen)
        elif (m := re.search(r"Account name: $", pending)):
            send("name", args.account_name); consumed = len(seen)
        elif (m := re.search(r"Provider \[1-(\d+)\]: $", pending)):
            rows = re.findall(r"^\s*(\d+)\) (.+?) \(([^)]+)\)\s*$", pending, re.M)
            pick = next((n for n, _label, pid in rows if pid == args.provider), None)
            if not pick:
                print(f"provider {args.provider} not offered; offered: {[r[2] for r in rows]}", file=sys.stderr)
                proc.kill(); return 3
            send("provider", pick); consumed = len(seen)
        elif re.search(r"Authentication \[1 = API key, 2 = subscription\]: $", pending):
            send("auth", "1"); consumed = len(seen)
        elif re.search(r"Base URL \[.*\]: $", pending):
            send("base", args.base_url); consumed = len(seen)
        elif re.search(r"API key \(stored by the local backend; never returned\): $", pending):
            send("key", key, shown="[key]"); consumed = len(seen)
        elif (m := re.search(r"Model \[1-(\d+)\]: $", pending)):
            rows = re.findall(r"^\s*(\d+)\) (.+?) \(([^)]+)\)\s*$", pending, re.M)
            pick = next((n for n, _label, mid in rows if mid == args.model), None)
            if not pick:
                print(f"model {args.model} not in verified list: {[r[2] for r in rows]}", file=sys.stderr)
                proc.kill(); return 4
            send("model", pick); consumed = len(seen)
        if proc.poll() is not None and not ready:
            break
    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    out = mask("\n".join(log))
    if args.transcript:
        open(args.transcript, "w", encoding="utf-8").write(out + "\n")
    print(out)
    print(f"wizard exit code: {proc.returncode}")
    return proc.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
