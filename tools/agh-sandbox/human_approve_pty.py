#!/usr/bin/env python3
"""Run tools/pk_human_approve.py under a real pseudo terminal the way a person would use it.

The script waits for the prompt that asks for the first 8 characters of the snapshot digest, reads the
digest that the CLI itself printed, pauses like a person reading it, types the first 8 characters key by
key, presses Enter, accepts the default reason and records every byte the terminal produced together with
its timestamp. Nothing is faked: the approval is the kernel's own `approval.decide` through the CLI.

Usage:
  python3 human_approve_pty.py --root <PK_ROOT> --script <kernel_next>/tools/pk_human_approve.py \
      --python <python> --out <transcript.json>
Writes <out> (JSON with timed chunks) and <out without .json>.txt (plain text transcript).
"""
import argparse
import fcntl
import json
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--out", required=True)
    ap.add_argument("--think", type=float, default=2.5, help="seconds the person looks at the snapshot")
    ap.add_argument("--key-delay", type=float, default=0.12)
    ap.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args()

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", LANG="C.UTF-8", LC_ALL="C.UTF-8", TERM="xterm-256color")
    cmd = [a.python, a.script, "--root", a.root]
    started = time.time()
    proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True,
                            start_new_session=True)
    os.close(slave)
    chunks, buf, state, typed = [], "", 0, None
    while time.time() - started < a.timeout:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            text = data.decode("utf-8", "replace")
            chunks.append([round(time.time() - started, 3), text])
            buf += text
        if state == 0 and "批准请输入快照摘要前" in buf:
            match = re.search(r"快照摘要:\s*(\S+)", ANSI.sub("", buf))
            if not match:
                break
            typed = match.group(1)[:8]
            time.sleep(a.think)
            for ch in typed:
                os.write(master, ch.encode())
                time.sleep(a.key_delay)
            time.sleep(0.5)
            os.write(master, b"\r")
            state, buf = 1, ""
        elif state == 1 and "批准理由" in buf:
            time.sleep(1.2)
            os.write(master, b"\r")
            state, buf = 2, ""
        if proc.poll() is not None and not ready:
            break
    try:
        code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = -9
    plain = ANSI.sub("", "".join(c[1] for c in chunks)).replace("\r\n", "\n").replace("\r", "")
    result = {"command": "python tools/pk_human_approve.py --root " + a.root, "typed_prefix": typed,
              "exit_code": code, "duration_s": round(time.time() - started, 2), "chunks": chunks}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    with open(re.sub(r"\.json$", "", a.out) + ".txt", "w", encoding="utf-8") as f:
        f.write("$ " + result["command"] + "\n" + plain)
    print(plain)
    print(f"[exit {code}; typed {typed!r}]")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
