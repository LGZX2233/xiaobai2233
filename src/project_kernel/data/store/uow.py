"""UnitOfWork: single short transaction, CAS, idempotency and one commit_seq.

The only commit/rollback owner. Writes revision/head/history/audit/receipt in
one transaction. A stable business rejection commits a rejected receipt +
audit event but advances no entity head; transient failures roll back and are
never recorded as a business rejection.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ...contracts.dto import CommandContext, CommandReceipt, Cursor, ObjectRef
from ...contracts.errors import (
    BlockError,
    KernelError,
    commit_outcome_unknown,
    idempotency_conflict,
    sqlite_busy,
    temporary_unavailable,
)
from .blockers import Blockers
from .outbox import Outbox
from .records import Records
from .source import SourceIngest
from .store import Store


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_command_id() -> str:
    return "cmd-" + uuid.uuid4().hex


@dataclass
class CommandOutcome:
    object_refs: tuple[ObjectRef, ...] = ()
    result_refs: tuple[ObjectRef, ...] = ()
    operation_id: str | None = None


@dataclass
class Handles:
    records: Records
    outbox: Outbox
    source: SourceIngest
    audit: Callable[..., None]
    outcome: CommandOutcome = field(default_factory=CommandOutcome)

    @property
    def blockers(self) -> Blockers:
        return Blockers(self.records)


class UnitOfWork:
    def __init__(self, store: Store, context: CommandContext, command_kind: str):
        self.store = store
        self.ctx = context
        self.command_kind = command_kind
        self._audit_buffer: list[tuple[str, str, Any, Any, Any]] = []
        self.did_commit = False

    def _existing_receipt(self) -> dict[str, Any] | None:
        return self.store.get_receipt(self.ctx.scope.principal_id, self.ctx.idempotency_key)

    def _check_idempotency(self) -> CommandReceipt | None:
        existing = self._existing_receipt()
        if existing is None:
            return None
        if existing.get("input_hash") != self.ctx.input_hash:
            raise KernelError(idempotency_conflict(
                f"idempotency key {self.ctx.idempotency_key} reused with different input"))
        return _receipt_from_dict(existing["receipt"])

    def _audit(self, event_type: str, payload: Any = None, event_schema: str = "v1",
               object_refs: Any = None, source_key: Any = None) -> None:
        self._audit_buffer.append((event_type, event_schema, object_refs, source_key, payload))

    def _begin(self) -> None:
        try:
            self.store.conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=False)

    def _rollback_before_commit(self) -> None:
        try:
            if self.store.conn.in_transaction:
                self.store.conn.execute("ROLLBACK")
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=False)

    def _raise_sqlite_failure(self, error: sqlite3.Error, *,
                              commit_started: bool) -> None:
        rolled_back = False
        try:
            if self.store.conn.in_transaction:
                self.store.conn.execute("ROLLBACK")
                rolled_back = True
        except sqlite3.Error:
            # A failed rollback after COMMIT started cannot establish its outcome.
            pass
        if commit_started and not rolled_back:
            raise KernelError(commit_outcome_unknown()) from error
        code = getattr(error, "sqlite_errorcode", None)
        if code is not None and (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise KernelError(sqlite_busy()) from error
        raise KernelError(temporary_unavailable(
            "Database transaction did not commit; retry with the original key")) from error

    def _commit(self) -> None:
        try:
            self.store.conn.execute("COMMIT")
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=True)
        self.did_commit = True

    def execute(self, callback: Callable[[Handles], None]) -> CommandReceipt:
        """Return a durable receipt; did_commit is false for replay or any failure.

        did_commit describes this invocation, including a newly committed business
        rejection. Callers starting external work also require an accepted receipt.
        It is not a durable execution lease or permission to retry unknown effects.
        """
        self.did_commit = False
        self._audit_buffer.clear()
        self.store._guard_write()
        try:
            dup = self._check_idempotency()
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=False)
        if dup is not None:
            return dup

        principal = self.ctx.scope.principal_id
        command_id = _new_command_id()
        self._begin()
        try:
            dup = self._check_idempotency()
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=False)
        except BaseException:
            self._rollback_before_commit()
            raise
        if dup is not None:
            self._rollback_before_commit()
            return dup

        try:
            # CR-004: allocation and all transaction writes share the write lock.
            commit_seq = self.store.next_commit_seq()
            handles = Handles(
                records=Records(self.store.conn, self.store.project_id, commit_seq,
                                command_id, principal),
                outbox=Outbox(self.store.conn),
                source=SourceIngest(self.store.conn, commit_seq),
                audit=self._audit,
            )
            callback(handles)
        except KernelError as error:
            self._rollback_before_commit()
            if error.error.retryable or error.error.category == "unknown":
                raise
            return self._commit_rejection(error.error, principal)
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=False)
        except BaseException:
            self._rollback_before_commit()
            raise

        try:
            receipt = self._write_commit(handles, commit_seq, command_id, principal)
        except sqlite3.Error as error:
            self._raise_sqlite_failure(error, commit_started=False)
        except BaseException:
            self._rollback_before_commit()
            raise
        self._commit()
        return receipt

    def _write_commit(self, handles: Handles, commit_seq: int, command_id: str,
                      principal: str) -> CommandReceipt:
        conn = self.store.conn
        conn.execute(
            "INSERT INTO commit_log (commit_seq, command_id, principal_id, committed_at)"
            " VALUES (?,?,?,?)",
            (commit_seq, command_id, principal, _utc_now()),
        )
        buffer = list(self._audit_buffer)
        if not buffer:
            buffer = [("command.committed", "v1", None, None, None)]
        for idx, (etype, eschema, objrefs, srckey, payload) in enumerate(buffer):
            conn.execute(
                "INSERT INTO audit_event (commit_seq, event_index, event_type, event_schema,"
                " object_refs, command_id, causal_refs, source_key, payload)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (commit_seq, idx, etype, eschema,
                 json.dumps(objrefs, ensure_ascii=False) if objrefs else None,
                 command_id, None,
                 json.dumps(srckey, ensure_ascii=False) if srckey else None,
                 json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None),
            )
        status = "accepted" if handles.outcome.operation_id else "committed"
        receipt = self._receipt(command_id, commit_seq, handles.outcome, principal, status)
        conn.execute(
            "INSERT INTO command_receipt (principal_id, idempotency_key, command_kind,"
            " input_hash, command_id, status, receipt_json, commit_seq) VALUES (?,?,?,?,?,?,?,?)",
            (principal, self.ctx.idempotency_key, self.command_kind, self.ctx.input_hash,
             command_id, status, json.dumps(receipt.to_dict(), ensure_ascii=False), commit_seq),
        )
        return receipt

    def _commit_rejection(self, error: BlockError, principal: str) -> CommandReceipt:
        conn = self.store.conn
        command_id = _new_command_id()
        self._begin()
        try:
            # Another invocation may have won the key while the first transaction
            # was rolled back. A rejection must obey the same replay/hash rules.
            dup = self._check_idempotency()
            if dup is not None:
                self._rollback_before_commit()
                return dup
            commit_seq = self.store.next_commit_seq()
            receipt = CommandReceipt(
                command_id=command_id, idempotency_key=self.ctx.idempotency_key,
                command=self.command_kind, status="rejected", commit_seq=str(commit_seq),
                event_cursor=Cursor(commit_seq=str(commit_seq), event_index=0),
                receipt_domain="project", store_id=self.store.store_id, error=error,
            )
            conn.execute(
                "INSERT INTO commit_log (commit_seq, command_id, principal_id, committed_at)"
                " VALUES (?,?,?,?)", (commit_seq, command_id, principal, _utc_now()))
            conn.execute(
                "INSERT INTO audit_event (commit_seq, event_index, event_type, event_schema,"
                " object_refs, command_id, causal_refs, source_key, payload)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (commit_seq, 0, "command.rejected", "v1", None, command_id, None, None,
                 json.dumps({"error": error.to_dict()}, ensure_ascii=False)))
            conn.execute(
                "INSERT INTO command_receipt (principal_id, idempotency_key, command_kind,"
                " input_hash, command_id, status, receipt_json, commit_seq) VALUES (?,?,?,?,?,?,?,?)",
                (principal, self.ctx.idempotency_key, self.command_kind, self.ctx.input_hash,
                 command_id, "rejected", json.dumps(receipt.to_dict(), ensure_ascii=False),
                 commit_seq))
        except sqlite3.Error as failure:
            self._raise_sqlite_failure(failure, commit_started=False)
        except BaseException:
            self._rollback_before_commit()
            raise
        self._commit()
        return receipt

    def _receipt(self, command_id: str, commit_seq: int, outcome: CommandOutcome,
                 principal: str, status: str) -> CommandReceipt:
        cursor = Cursor(commit_seq=str(commit_seq), event_index=max(len(self._audit_buffer) - 1, 0))
        return CommandReceipt(
            command_id=command_id, idempotency_key=self.ctx.idempotency_key,
            command=self.command_kind, status=status, commit_seq=str(commit_seq),
            event_cursor=cursor, object_refs=outcome.object_refs, result_refs=outcome.result_refs,
            receipt_domain="project", store_id=self.store.store_id,
            operation_id=outcome.operation_id,
        )


def _receipt_from_dict(data: dict[str, Any]) -> CommandReceipt:
    return CommandReceipt(
        command_id=data["command_id"], idempotency_key=data["idempotency_key"],
        command=data["command"], status=data["status"], commit_seq=data["commit_seq"],
        event_cursor=Cursor(data["event_cursor"]["commit_seq"], data["event_cursor"]["event_index"]),
        object_refs=tuple(ObjectRef.from_dict(r) for r in data.get("object_refs", [])),
        result_refs=tuple(ObjectRef.from_dict(r) for r in data.get("result_refs", [])),
        committed_at=data.get("committed_at", ""), receipt_domain=data.get("receipt_domain", "project"),
        store_id=data.get("store_id", ""), operation_id=data.get("operation_id"),
        error=BlockError.from_dict(data["error"]) if data.get("error") is not None else None,
    )
