"""Shared helpers for P01 tests. All stores use tmp_path; never the CWD."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from project_kernel.contracts.dto import CommandContext, ResolvedScope
from project_kernel.contracts import sha256_digest
from project_kernel.data.store.store import Store


def make_store(tmp_path: Path, project_id: str = "proj-a", store_id: str = "store-a",
               read_only: bool = False) -> Store:
    path = tmp_path / f"{project_id}.sqlite"
    return Store.open_project(path, project_id, store_id, read_only=read_only)


def make_context(scope: ResolvedScope | None = None, key: str = "key-1",
                 input_hash: str | None = None) -> CommandContext:
    if scope is None:
        scope = ResolvedScope(project_id="proj-a", store_id="store-a", principal_id="user-1",
                              capabilities=frozenset({"project.read", "design.write"}), mode="test")
    ih = input_hash or sha256_digest({"key": key})
    return CommandContext(scope=scope, command_id="cmd-test", idempotency_key=key,
                          input_hash=ih)


def record_payload(title: str) -> dict:
    return {"title": title, "goal": "goal", "mode": "test"}
