"""Append-only blocker states with a current index in the caller's transaction."""
from __future__ import annotations

import json

from ...contracts.dto import ObjectRef
from ...contracts.errors import KernelError, invalid_input, scope_mismatch, stale_revision
from .records import Records


class Blockers:
    """Preserve exact opening and resolution evidence; never commit independently."""

    def __init__(self, records: Records):
        self.records = records

    def _checked(self, ref: ObjectRef, kind: str | None = None) -> dict:
        if ref.project_id != self.records.project_id:
            raise KernelError(scope_mismatch("blocker evidence belongs to another project"))
        if kind is not None and ref.object_type != kind:
            raise KernelError(invalid_input(f"expected {kind} reference"))
        return self.records.read(ref.object_type, ref.object_id, revision_id=ref.revision_id)

    def open(self, blocker_id: str, task_ref: ObjectRef, code: str,
             evidence_ref: ObjectRef) -> ObjectRef:
        self._checked(task_ref, "task")
        self._checked(evidence_ref)
        if not isinstance(code, str) or not code.strip():
            raise KernelError(invalid_input("blocker code is required"))
        if self.records.conn.execute(
                "SELECT 1 FROM blocker WHERE project_id=? AND blocker_id=?",
                (self.records.project_id, blocker_id)).fetchone():
            raise KernelError(stale_revision("blocker already exists"))
        # Validate the durable object identifier before mutating any table.
        ObjectRef(self.records.project_id, "blocker", blocker_id, "rev-1")
        body = {"blocker_id": blocker_id, "task_id": task_ref.object_id,
                "task_ref": task_ref.to_dict(), "code": code, "status": "open",
                "evidence_ref": evidence_ref.to_dict(), "resolution_ref": None}
        ref = self.records.append_revision("blocker", blocker_id, body, "blocker.v1")
        self.records.publish_head(ref, "current", "0")
        self.records.conn.execute(
            "INSERT INTO blocker(project_id,blocker_id,task_id,code,evidence_ref,resolution_ref)"
            " VALUES(?,?,?,?,?,NULL)",
            (self.records.project_id, blocker_id, task_ref.object_id, code,
             json.dumps(evidence_ref.to_dict())))
        return ref

    def resolve(self, blocker_ref: ObjectRef, resolution_ref: ObjectRef,
                *, expected_head_version: str) -> ObjectRef:
        body = self._checked(blocker_ref, "blocker")["payload"]
        self._checked(resolution_ref)
        head = self.records.conn.execute(
            "SELECT revision_id,head_version FROM entity_head"
            " WHERE project_id=? AND type='blocker' AND object_id=? AND pointer_name='current'",
            (self.records.project_id, blocker_ref.object_id)).fetchone()
        if (head is None or head[0] != blocker_ref.revision_id
                or str(head[1]) != expected_head_version or body["status"] != "open"):
            raise KernelError(stale_revision("blocker changed or is already resolved"))
        ref = self.records.append_revision(
            "blocker", blocker_ref.object_id,
            {**body, "status": "resolved", "resolution_ref": resolution_ref.to_dict()},
            "blocker.v1", parent_ref=blocker_ref)
        self.records.publish_head(ref, "current", expected_head_version)
        self.records.conn.execute(
            "UPDATE blocker SET resolution_ref=? WHERE project_id=? AND blocker_id=?",
            (json.dumps(resolution_ref.to_dict()), self.records.project_id, blocker_ref.object_id))
        return ref
