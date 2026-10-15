"""Typed records repository: append_revision / publish_head / read.

Bound to the caller's connection; never commits and never opens a new write
connection. publish_head performs a CAS against the caller-provided
expected_head_version and returns STALE_REVISION on mismatch.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from ...contracts import sha256_digest
from ...contracts.dto import ObjectRef
from ...contracts.errors import KernelError, reference_not_found, stale_revision


class HeadReceipt:
    def __init__(self, object_ref: ObjectRef, pointer_name: str, head_version: int,
                 commit_seq: int):
        self.object_ref = object_ref
        self.pointer_name = pointer_name
        self.head_version = head_version
        self.commit_seq = commit_seq


class Records:
    def __init__(self, conn: sqlite3.Connection, project_id: str, commit_seq: int,
                 command_id: str, principal_id: str):
        self.conn = conn
        self.project_id = project_id
        self.commit_seq = commit_seq
        self.command_id = command_id
        self.principal_id = principal_id

    def append_revision(self, object_type: str, object_id: str, typed_payload: Any,
                        payload_schema: str, parent_ref: ObjectRef | None = None) -> ObjectRef:
        self.conn.execute(
            "INSERT OR IGNORE INTO entity (project_id, type, object_id, created_seq)"
            " VALUES (?,?,?,?)",
            (self.project_id, object_type, object_id, self.commit_seq),
        )
        row = self.conn.execute(
            "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM revision"
            " WHERE project_id=? AND type=? AND object_id=?",
            (self.project_id, object_type, object_id),
        ).fetchone()
        ordinal = int(row[0])
        revision_id = f"rev-{ordinal}"
        payload_json = json.dumps(typed_payload, ensure_ascii=False, separators=(",", ":"))
        digest = sha256_digest(typed_payload)
        parent_json = json.dumps(parent_ref.to_dict(), ensure_ascii=False) if parent_ref else None
        self.conn.execute(
            "INSERT INTO revision (project_id, type, object_id, revision_id, ordinal,"
            " parent_ref, payload_schema, payload_json, digest, commit_seq, command_id, principal_id)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.project_id, object_type, object_id, revision_id, ordinal, parent_json,
             payload_schema, payload_json, digest, self.commit_seq, self.command_id,
             self.principal_id),
        )
        return ObjectRef(self.project_id, object_type, object_id, revision_id)

    def publish_head(self, object_ref: ObjectRef, pointer_name: str,
                     expected_head_version: str | None = None) -> HeadReceipt:
        current = self.conn.execute(
            "SELECT head_version, revision_id FROM entity_head"
            " WHERE project_id=? AND type=? AND object_id=? AND pointer_name=?",
            (object_ref.project_id, object_ref.object_type, object_ref.object_id, pointer_name),
        ).fetchone()

        if current is None:
            if expected_head_version is not None and expected_head_version != "0":
                raise KernelError(stale_revision("pointer does not exist yet"))
            new_version = 1
        else:
            cur_version = int(current[0])
            if expected_head_version is None or int(expected_head_version) != cur_version:
                raise KernelError(stale_revision(
                    f"expected head_version {expected_head_version}, actual {cur_version}"))
            new_version = cur_version + 1

        self.conn.execute(
            "INSERT INTO entity_head (project_id, type, object_id, pointer_name,"
            " revision_id, head_version, updated_seq)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(project_id, type, object_id, pointer_name)"
            " DO UPDATE SET revision_id=excluded.revision_id, head_version=excluded.head_version,"
            " updated_seq=excluded.updated_seq",
            (object_ref.project_id, object_ref.object_type, object_ref.object_id, pointer_name,
             object_ref.revision_id, new_version, self.commit_seq),
        )
        self.conn.execute(
            "INSERT INTO head_history (project_id, type, object_id, pointer_name, commit_seq,"
            " revision_id, head_version) VALUES (?,?,?,?,?,?,?)",
            (object_ref.project_id, object_ref.object_type, object_ref.object_id, pointer_name,
             self.commit_seq, object_ref.revision_id, new_version),
        )
        return HeadReceipt(object_ref, pointer_name, new_version, self.commit_seq)

    def read(self, object_type: str, object_id: str, revision_id: str | None = None,
             as_of_seq: int | None = None, pointer_name: str | None = None) -> dict[str, Any]:
        if revision_id is not None:
            row = self.conn.execute(
                "SELECT payload_json, digest, commit_seq FROM revision"
                " WHERE project_id=? AND type=? AND object_id=? AND revision_id=?",
                (self.project_id, object_type, object_id, revision_id),
            ).fetchone()
        elif as_of_seq is not None and pointer_name is not None:
            row = self.conn.execute(
                "SELECT r.payload_json, r.digest, r.commit_seq FROM head_history h"
                " JOIN revision r ON r.project_id=h.project_id AND r.type=h.type"
                " AND r.object_id=h.object_id AND r.revision_id=h.revision_id"
                " WHERE h.project_id=? AND h.type=? AND h.object_id=? AND h.pointer_name=?"
                " AND h.commit_seq<=? ORDER BY h.commit_seq DESC LIMIT 1",
                (self.project_id, object_type, object_id, pointer_name, as_of_seq),
            ).fetchone()
        else:
            raise ValueError("read requires revision_id or (as_of_seq, pointer_name)")
        if row is None:
            raise KernelError(reference_not_found(f"{object_type}/{object_id} not found"))
        return {"payload": json.loads(row[0]), "digest": row[1], "commit_seq": int(row[2])}
