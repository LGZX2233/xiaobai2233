"""P06 helpers: build ledger fixtures with the P01 store's public write API.

These tests intentionally depend only on P00 contracts + the P01 store/UoW so the
P06 read models are exercised against a real temporary SQLite ledger without
coupling to P02/P03/P04 service modules.
"""
from __future__ import annotations

from typing import Any

from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import CommandContext, ObjectRef, ResolvedScope
from project_kernel.data.store.store import Store
from project_kernel.data.store.uow import UnitOfWork

PROJ = "proj-a"


def scope(capabilities: frozenset[str] | None = None) -> ResolvedScope:
    return ResolvedScope(project_id=PROJ, store_id="store-a", principal_id="user-1",
                         capabilities=capabilities or frozenset({"project.read", "design.write"}),
                         mode="test")


def ctx(key: str) -> CommandContext:
    return CommandContext(scope=scope(), command_id="cmd-" + key, idempotency_key=key,
                          input_hash=sha256_digest({"key": key}))


def ref(object_type: str, object_id: str, revision_id: str = "rev-1") -> dict[str, str]:
    return {"project_id": PROJ, "object_type": object_type, "object_id": object_id,
            "revision_id": revision_id}


def append_revision(store: Store, key: str, object_type: str, object_id: str,
                    payload: dict[str, Any], pointer: str = "current") -> ObjectRef:
    """Append one revision and publish it to ``pointer`` with a real head CAS."""
    existing = store.get_head(object_type, object_id, pointer)
    expected = str(existing["head_version"]) if existing else None
    holder: dict[str, ObjectRef] = {}

    def cb(h) -> None:
        record = h.records.append_revision(object_type, object_id, payload,
                                           f"{object_type}.v1")
        h.records.publish_head(record, pointer, expected_head_version=expected)
        holder["ref"] = record

    UnitOfWork(store, ctx(key), f"{object_type}.write").execute(cb)
    return holder["ref"]


def add_task(store: Store, key: str, task_id: str, phase: str = "draft",
             extra: dict[str, Any] | None = None) -> ObjectRef:
    payload = {"task_id": task_id, "title": task_id, "goal": "g", "phase": phase,
               "requirement_refs": []}
    payload.update(extra or {})
    return append_revision(store, key, "task", task_id, payload)
