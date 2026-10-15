"""Test-only stdio host for the shipped composition root; owns no application bin."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from project_kernel.bootstrap import build_server, InvocationContextRegistry
from project_kernel.contracts import ALL_CAPABILITIES
from project_kernel.data.store.store import Store
from project_kernel.interfaces.rpc.framing import decode_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--drop-first-command", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root.is_relative_to(ROOT / ".validation-tmp") or root.is_relative_to(Path(tempfile.gettempdir()).resolve())):
        parser.error("the host requires an explicit kernel validation temporary root")
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    store = Store.open_project(root / "protocol.sqlite", "protocol-project", "protocol-store")
    registry = InvocationContextRegistry(handle_factory=lambda: "test-protocol-handle")
    registry.mint("test-protocol-user", ALL_CAPABILITIES, project_id=store.project_id)
    server = build_server(store, principal="test-protocol-user", contexts=registry, mode="test")
    dropped = False
    try:
        while chunk := sys.stdin.buffer.read1(4096):
            for response in server.feed(chunk):
                value = decode_frame(response)
                if args.drop_first_command and not dropped and "receipt" in value.get("result", {}):
                    dropped = True
                    print("test: committed response deliberately dropped", file=sys.stderr, flush=True)
                    continue
                sys.stdout.buffer.write(response)
                sys.stdout.buffer.flush()
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
