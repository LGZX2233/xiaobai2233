"""Read-only QueryService over the P01 store.

Queries run SELECT-only against the same read connection; they never run DDL,
never call migrations, never launch shell probes, and never advance writes.
Every read model is scoped by an as_of watermark and returns the QueryEnvelope
fields (source_watermarks/freshness/completeness/gaps/next_page_token) plus the
query payload under ``data`` (legacy top-level aliases kept for P10 callers).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from ...contracts import sha256_digest
from ...contracts.dto import Cursor, ObjectRef
from ...contracts.errors import KernelError, archive_partial, invalid_input, reference_not_found
from ...data.store.store import Store
from . import links
from .watermarks import (
    COMPLETE,
    INCOMPLETE,
    PROJECTION_VERSION,
    ReadEnvelope,
    decode_page_token,
    encode_page_token,
)

_APPROVAL_STATUSES = ("pending", "approved", "rejected", "expired", "superseded", "revoked")

_CATEGORY_BY_TYPE = {
    "requirement": "requirement",
    "design": "design",
    "execution_packet": "dispatch",
    "approval": "approval",
    "delivery": "delivery",
    "verification": "verification",
    "attempt": "attempt",
    "task": "task",
    "artifact": "artifact",
    "archive_manifest": "archive",
}

_FACT_STATES = ("satisfied", "missing", "too_old", "unknown", "not_checked")


def _category(object_type: str) -> str:
    return _CATEGORY_BY_TYPE.get(object_type, "revision")


def _normalize_fact(fact: Any) -> dict[str, Any]:
    """Project an EnvironmentSnapshot fact onto the report fields (04 §5)."""
    if not isinstance(fact, dict):
        return {"requirement": None, "required_version": None, "installed_version": None,
                "path": None, "state": "unknown", "detail": fact}
    state = fact.get("state")
    if state not in _FACT_STATES:
        state = "unknown"
    return {
        "requirement": fact.get("requirement") or fact.get("name")
        or fact.get("requirement_ref"),
        "required_version": fact.get("required_version") or fact.get("requirement_version"),
        "installed_version": (fact.get("installed_version") or fact.get("actual_version")
                              or fact.get("version")),
        "path": fact.get("path") or fact.get("locator"),
        "state": state,
        "detail": fact,
    }


class QueryService:
    def __init__(self, store: Store):
        self.store = store

    # -- read-transaction / envelope helpers --------------------------------
    @contextmanager
    def _read_tx(self) -> Iterator[None]:
        """Fix the first page inside one short SQLite read transaction."""
        conn = self.store.conn
        started = False
        if not conn.in_transaction:
            conn.execute("BEGIN DEFERRED")
            started = True
        try:
            yield
        finally:
            if started:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass

    def _envelope(self) -> ReadEnvelope:
        return ReadEnvelope(self.store.conn, self.store.project_id, self.store.store_id)

    def _filter_hash(self, query: str, filters: Any) -> str:
        return sha256_digest({"query": query, "filters": filters})

    # command.receipt ------------------------------------------------------
    def command_receipt(self, principal_id: str, idempotency_key: str) -> dict[str, Any] | None:
        return self.store.get_receipt(principal_id, idempotency_key)

    # events.read ----------------------------------------------------------
    def events_read(self, after: Cursor, *, as_of_seq: str | int | None = None,
                    limit: int | None = None) -> list[dict[str, Any]]:
        with self._read_tx():
            as_of = self._envelope().resolve_as_of(as_of_seq)
            sql = ("SELECT commit_seq, event_index, event_type, event_schema, object_refs, command_id"
                   " FROM audit_event WHERE (commit_seq > ? OR (commit_seq = ? AND event_index > ?))"
                   " AND commit_seq <= ? ORDER BY commit_seq, event_index")
            params = [int(after.commit_seq), int(after.commit_seq), after.event_index, as_of]
            if limit is not None:
                if not isinstance(limit, int) or not 1 <= limit <= 1000:
                    raise KernelError(invalid_input("event limit must be between 1 and 1000"))
                sql += " LIMIT ?"
                params.append(limit)
            rows = self.store.conn.execute(sql, params).fetchall()
            return [{"commit_seq": str(r[0]), "event_index": r[1], "event_type": r[2],
                     "event_schema": r[3], "object_refs": json.loads(r[4]) if r[4] else [],
                     "command_id": r[5]} for r in rows]

    # operation.status -----------------------------------------------------
    def operation_status(self, operation_id: str, *,
                         as_of_seq: str | int | None = None) -> dict[str, Any]:
        with self._read_tx():
            as_of = self._envelope().resolve_as_of(as_of_seq)
            for kind in ("delivery","evidence_operation","dataset_export_operation","environment_probe","verification_operation","attempt","project_binding_operation"):
                revision=self.store.head_as_of(kind,operation_id,"current",as_of)
                if revision is not None:
                    rev=self.store.get_revision(ObjectRef(self.store.project_id,kind,operation_id,revision))
                    return {"operation_id":operation_id,"operation_kind":kind,**rev["payload"]}
            raise KernelError(reference_not_found(f"operation {operation_id} not found"))

    # -- ledger read helpers ------------------------------------------------
    def _current_heads(self, object_type: str, pointer: str,
                       as_of: int) -> list[tuple[str, str, int]]:
        rows = self.store.conn.execute(
            "SELECT h.object_id, h.revision_id, h.commit_seq FROM head_history h"
            " JOIN (SELECT object_id, MAX(commit_seq) AS mc FROM head_history"
            "        WHERE type=? AND pointer_name=? AND commit_seq<=? GROUP BY object_id) m"
            "   ON m.object_id=h.object_id AND m.mc=h.commit_seq"
            " WHERE h.type=? AND h.pointer_name=?",
            (object_type, pointer, as_of, object_type, pointer)).fetchall()
        return [(r[0], r[1], int(r[2])) for r in rows]

    def _payload(self, object_type: str, object_id: str,
                 revision_id: str) -> dict[str, Any] | None:
        row = self.store.conn.execute(
            "SELECT payload_json FROM revision WHERE project_id=? AND type=? AND object_id=?"
            " AND revision_id=?",
            (self.store.project_id, object_type, object_id, revision_id)).fetchone()
        return json.loads(row[0]) if row else None

    def _all_objects_at(self, object_type: str, as_of: int) -> list[tuple[str, int]]:
        rows = self.store.conn.execute(
            "SELECT object_id, MIN(created_seq) FROM entity WHERE type=? AND created_seq<=?"
            " GROUP BY object_id", (object_type, as_of)).fetchall()
        return [(r[0], int(r[1])) for r in rows]

    def _latest_revision_at(self, object_type: str, object_id: str,
                            as_of: int) -> tuple[str, dict[str, Any], int] | None:
        row = self.store.conn.execute(
            "SELECT revision_id, payload_json, commit_seq FROM revision"
            " WHERE project_id=? AND type=? AND object_id=? AND commit_seq<=?"
            " ORDER BY commit_seq DESC, ordinal DESC LIMIT 1",
            (self.store.project_id, object_type, object_id, as_of)).fetchone()
        if row is None:
            return None
        return row[0], json.loads(row[1]), int(row[2])

    def _revisions_at(self, object_type: str,
                      as_of: int) -> list[tuple[str, str, dict[str, Any], int, int]]:
        rows = self.store.conn.execute(
            "SELECT object_id, revision_id, payload_json, commit_seq, ordinal FROM revision"
            " WHERE project_id=? AND type=? AND commit_seq<=? ORDER BY commit_seq, ordinal",
            (self.store.project_id, object_type, as_of)).fetchall()
        return [(r[0], r[1], json.loads(r[2]), int(r[3]), int(r[4])) for r in rows]

    def _page(self, items: list[dict[str, Any]], *, query: str, filters: dict[str, Any],
              as_of: int, limit: int, page_token: str | None,
              last_key_field: str = "_sort") -> tuple[list[dict[str, Any]], str | None, int]:
        filter_hash = self._filter_hash(query, filters)
        cursor_key: str | None = None
        if page_token:
            token_as_of, cursor_key = decode_page_token(
                page_token, query=query, project_id=self.store.project_id,
                store_id=self.store.store_id, filter_hash=filter_hash, requested_as_of=as_of)
            # A token always continues at its own watermark; never jump ahead of it.
            as_of = min(as_of, token_as_of)
        # Re-apply the effective watermark so a continuation page cannot include
        # rows committed after the first page fixed its as_of.
        items = [i for i in items if int(i.get("commit_seq", 0)) <= as_of]
        if cursor_key is not None:
            items = [i for i in items if str(i.get(last_key_field, "")) < cursor_key]
        if len(items) > limit:
            page = items[:limit]
            next_token = encode_page_token(
                query=query, project_id=self.store.project_id, store_id=self.store.store_id,
                filter_hash=filter_hash, as_of_seq=as_of,
                last_key=str(page[-1].get(last_key_field, "")))
        else:
            page = items
            next_token = None
        return page, next_token, as_of

    # project.overview -----------------------------------------------------
    def project_overview(self, *, as_of_seq: str | int | None = None) -> dict[str, Any]:
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            counts: dict[str, int] = {}
            for row in self.store.conn.execute(
                    "SELECT type, COUNT(*) FROM entity WHERE created_seq<=? GROUP BY type",
                    (as_of,)):
                counts[row[0]] = int(row[1])
            phases: dict[str, int] = {}
            for object_id, _ in self._all_objects_at("task", as_of):
                latest = self._latest_revision_at("task", object_id, as_of)
                if latest is not None and latest[1].get("phase"):
                    phase = latest[1]["phase"]
                    phases[phase] = phases.get(phase, 0) + 1
            blockers = []
            known = {row[0] for row in self.store.conn.execute(
                "SELECT object_id FROM entity WHERE project_id=? AND type='blocker'",
                (self.store.project_id,))}
            for oid, rid, seq in self._current_heads("blocker", "current", as_of):
                body = self._payload("blocker", oid, rid) or {}
                if body.get("status") == "open":
                    blockers.append({**body, "revision_id": rid, "commit_seq": str(seq)})
            legacy = self.store.conn.execute(
                "SELECT blocker_id,task_id,code,evidence_ref,resolution_ref FROM blocker"
                " WHERE project_id=? ORDER BY blocker_id", (self.store.project_id,)).fetchall()
            legacy = [row for row in legacy if row[0] not in known]
            blocker_history_unknown = bool(legacy) and as_of < env.head_seq()
            if not blocker_history_unknown:
                blockers.extend({"blocker_id": row[0], "task_id": row[1], "code": row[2],
                                 "history_state": "unavailable"}
                                for row in legacy if row[4] is None)
            blockers.sort(key=lambda body: body["blocker_id"])
            watermarks = env.source_watermarks(as_of)
            source_gaps = list(watermarks["gaps"])
            row = self.store.conn.execute(
                "SELECT COALESCE(MAX(commit_seq), 0) FROM commit_log WHERE commit_seq<=?",
                (as_of,)).fetchone()
            last_commit = int(row[0])
            recent = int(self.store.conn.execute(
                "SELECT COUNT(*) FROM revision WHERE commit_seq=?",
                (last_commit,)).fetchone()[0]) if last_commit else 0
            data = {"object_counts": counts, "phases": phases, "blockers": blockers,
                    "source_gaps": source_gaps, "recent_changes": recent,
                    "last_commit_seq": str(last_commit),
                    "completeness": "complete"}
            result = env.finalize("project.overview", data, as_of_seq=as_of, watermarks=watermarks,
                                  required_missing=[b["code"] for b in blockers] +
                                  (["blocker_history_unavailable"] if blocker_history_unknown else []))
            data["completeness"] = result["completeness"]
            return result
        return {}  # pragma: no cover - the with-block always returns

    # project.timeline -----------------------------------------------------
    def project_timeline(self, object_type: str | None = None, *,
                         as_of_seq: str | int | None = None,
                         page_token: str | None = None, limit: int = 100) -> dict[str, Any]:
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise KernelError(invalid_input("limit must be between 1 and 1000"))
        env = self._envelope()
        with self._read_tx():
            if page_token:
                token_as_of,_=decode_page_token(page_token,query="project.timeline",
                    project_id=self.store.project_id,store_id=self.store.store_id,
                    filter_hash=self._filter_hash("project.timeline",{"object_type": object_type, "limit": limit}),
                    requested_as_of=int(as_of_seq) if as_of_seq is not None else None)
                as_of_seq=token_as_of
            as_of = env.resolve_as_of(as_of_seq)
            items: list[dict[str, Any]] = []

            rev_sql = ("SELECT type, object_id, revision_id, commit_seq, ordinal FROM revision"
                       " WHERE commit_seq<=?")
            params: list[Any] = [as_of]
            if object_type:
                rev_sql += " AND type=?"
                params.append(object_type)
            for rtype, oid, rid, cseq, ordinal in self.store.conn.execute(rev_sql, params):
                items.append({"kind": "revision", "category": _category(rtype),
                              "commit_seq": str(cseq), "object_type": rtype,
                              "object_id": oid, "revision_id": rid, "ordinal": int(ordinal),
                              "_sort": f"2:{int(cseq):020d}:{int(ordinal):020d}:{rtype}:{oid}:{rid}"})

            head_sql = ("SELECT type, object_id, pointer_name, commit_seq, revision_id,"
                        " head_version FROM head_history WHERE commit_seq<=?")
            head_params: list[Any] = [as_of]
            if object_type:
                head_sql += " AND type=?"
                head_params.append(object_type)
            for htype, oid, pointer, cseq, rid, hver in self.store.conn.execute(
                    head_sql, head_params):
                items.append({"kind": "head", "category": _category(htype),
                              "commit_seq": str(cseq), "object_type": htype,
                              "object_id": oid, "pointer_name": pointer, "revision_id": rid,
                              "head_version": int(hver),
                              "_sort": f"1:{int(cseq):020d}:{int(hver):020d}:{htype}:{oid}:{pointer}"})

            for cseq, eidx, etype, command_id, refs_json in self.store.conn.execute(
                    "SELECT commit_seq, event_index, event_type, command_id, object_refs"
                    " FROM audit_event WHERE commit_seq<=?", (as_of,)):
                refs = json.loads(refs_json) if refs_json else []
                if object_type and not any(isinstance(r, dict)
                                           and r.get("object_type") == object_type for r in refs):
                    continue
                items.append({"kind": "event", "commit_seq": str(cseq), "event_index": int(eidx),
                              "event_type": etype, "command_id": command_id, "object_refs": refs,
                              "_sort": f"0:{int(cseq):020d}:{int(eidx):020d}:{etype}:{command_id}"})

            items.sort(key=lambda i: str(i["_sort"]), reverse=True)
            page, next_token, as_of = self._page(
                items, query="project.timeline",
                filters={"object_type": object_type, "limit": limit},
                as_of=as_of, limit=limit, page_token=page_token)
            for item in page:
                item.pop("_sort", None)
            data = {"events": page, "count": len(page), "object_type": object_type}
            return env.finalize("project.timeline", data, as_of_seq=as_of,
                                next_page_token=next_token)
        return {}  # pragma: no cover

    # project.trace --------------------------------------------------------
    def project_trace(self, root_ref: dict[str, Any], direction: str = "both",
                      max_depth: int = 3, *, as_of_seq: str | int | None = None) -> dict[str, Any]:
        if direction not in ("incoming", "outgoing", "both"):
            raise KernelError(invalid_input("direction must be incoming/outgoing/both"))
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 20:
            raise KernelError(invalid_input("max_depth must be between 1 and 20"))
        try:
            root = ObjectRef.from_dict(root_ref)
        except (KeyError, TypeError, ValueError) as exc:
            raise KernelError(invalid_input("root_ref must be an object_ref")) from exc
        if root.project_id != self.store.project_id:
            raise KernelError(invalid_input("root_ref belongs to another project"))
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            graph = links.build_graph(self.store.conn, self.store.project_id, as_of)
            walked = links.walk(graph, root.to_dict(), direction=direction, max_depth=max_depth)
            data = {**walked, "node_count": len(walked["nodes"]) + 1,
                    "edge_count": len(walked["edges"])}
            extra_gaps: list[Any] = []
            if walked["truncated"]:
                extra_gaps.append({"reason": "trace_truncated",
                                   "detail": "max_depth or revision scan limit reached;"
                                             " the graph is explicitly partial"})
            return env.finalize("project.trace", data, as_of_seq=as_of, extra_gaps=extra_gaps)
        return {}  # pragma: no cover

    # requirements.coverage ------------------------------------------------
    def requirements_coverage(
            self, requirement_refs: list[dict[str, Any]] | None = None, *,
            as_of_seq: str | int | None = None) -> dict[str, Any]:
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            if requirement_refs:
                req_ids = sorted({ObjectRef.from_dict(r).object_id for r in requirement_refs})
            else:
                req_ids = sorted(oid for oid, _, _ in
                                 self._current_heads("requirement", "current", as_of))
            packets = self._current_heads("execution_packet", "current", as_of)
            referenced: dict[str, list[str]] = {rid: [] for rid in req_ids}
            for packet_id, revision_id, _ in packets:
                payload = self._payload("execution_packet", packet_id, revision_id) or {}
                for ref in payload.get("requirement_refs", []):
                    oid = ref.get("object_id") if isinstance(ref, dict) else None
                    if oid in referenced and packet_id not in referenced[oid]:
                        referenced[oid].append(packet_id)
            requirements: list[dict[str, Any]] = []
            not_applicable: list[str] = []
            uncovered: list[str] = []
            covered: list[str] = []
            for rid in req_ids:
                packets_for = sorted(referenced[rid])
                if packets_for:
                    status = "covered"
                    covered.append(rid)
                else:
                    # Zero-link requirement: it stays in the denominator and is
                    # explicitly reported as N/A instead of being skipped.
                    status = "not_applicable"
                    not_applicable.append(rid)
                    uncovered.append(rid)
                requirements.append({"object_id": rid, "link_count": len(packets_for),
                                     "linked_packets": packets_for, "coverage": status,
                                     "not_applicable": not packets_for,
                                     "reason": None if packets_for
                                     else "no_linked_acceptance_or_packet"})
            data = {"denominator": len(req_ids), "covered": len(covered),
                    "uncovered": uncovered, "not_applicable": len(not_applicable),
                    "not_applicable_ids": not_applicable, "requirements": requirements,
                    "as_of_seq": str(as_of)}
            return env.finalize("requirements.coverage", data, as_of_seq=as_of)
        return {}  # pragma: no cover

    # attempts.compare -----------------------------------------------------
    def attempts_compare(self, task_ref: dict[str, Any], *,
                         as_of_seq: str | int | None = None) -> dict[str, Any]:
        task = ObjectRef.from_dict(task_ref)
        if task.project_id != self.store.project_id:
            raise KernelError(invalid_input("task_ref belongs to another project"))
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)

            task_packets: set[str] = set()
            for packet_id, revision_id, _ in self._current_heads(
                    "execution_packet", "current", as_of):
                payload = self._payload("execution_packet", packet_id, revision_id) or {}
                tref = payload.get("task_ref")
                if isinstance(tref, dict) and tref.get("object_id") == task.object_id:
                    task_packets.add(packet_id)

            # Linkage lives on earlier revisions (settle revisions only carry the
            # status), so scan the whole revision chain, not just the current head.
            by_attempt: dict[str, list[tuple[str, str, dict[str, Any], int, int]]] = {}
            for row in self._revisions_at("attempt", as_of):
                by_attempt.setdefault(row[0], []).append(row)
            index_link: dict[str, str] = {}
            for attempt_id, task_id, packet_ref in self.store.conn.execute(
                    "SELECT attempt_id, task_id, packet_ref FROM attempt_index").fetchall():
                if task_id == task.object_id:
                    index_link[attempt_id] = packet_ref

            attempts: list[dict[str, Any]] = []
            for attempt_id in sorted(set(by_attempt) | set(index_link)):
                revisions = by_attempt.get(attempt_id, [])
                packet_id: str | None = None
                belongs = attempt_id in index_link
                for _, _, rev_payload, _, _ in revisions:
                    tref = rev_payload.get("task_ref")
                    pref = rev_payload.get("packet_ref")
                    if isinstance(pref, dict) and pref.get("object_id") in task_packets:
                        belongs = True
                        packet_id = packet_id or pref["object_id"]
                    elif isinstance(pref, dict) and attempt_id in index_link:
                        packet_id = packet_id or pref.get("object_id")
                    if isinstance(tref, dict) and tref.get("object_id") == task.object_id:
                        belongs = True
                if not belongs or not revisions:
                    continue
                latest = revisions[-1][2]
                attempts.append(self._describe_attempt(attempt_id, packet_id, latest,
                                                       revisions, as_of))

            attempts.sort(key=lambda a: a["attempt_id"])
            groups: dict[str, list[str]] = {}
            for attempt in attempts:
                groups.setdefault(attempt["packet_id"] or "unlinked", []).append(attempt["attempt_id"])

            reported: list[dict[str, Any]] = []
            unknown: list[dict[str, Any]] = []
            dedup: list[dict[str, Any]] = []
            seen_usage_keys: set[str] = set()
            for attempt in attempts:
                cost = attempt.pop("_cost")
                usage_key = attempt.pop("_usage_key")
                if usage_key and usage_key in seen_usage_keys:
                    dedup.append({"attempt_id": attempt["attempt_id"], "usage_key": usage_key,
                                  "reason": "duplicate_source_redelivery"})
                    attempt["cost"] = {"state": "deduplicated",
                                       "reason": "duplicate_source_redelivery"}
                    continue
                if usage_key:
                    seen_usage_keys.add(usage_key)
                if cost is None:
                    attempt["cost"] = {"state": "unknown", "reason": "usage_not_reported"}
                    unknown.append({"attempt_id": attempt["attempt_id"],
                                    "reason": "usage_not_reported"})
                else:
                    attempt["cost"] = {"state": "reported", "amount": cost}
                    reported.append({"attempt_id": attempt["attempt_id"], "amount": cost,
                                     "formula_version": "p06-attempt-cost-1.0.0"})

            total: str | None = None
            if reported and not unknown:
                try:
                    total = str(sum(int(r["amount"]) for r in reported))
                except (TypeError, ValueError):
                    total = None

            if not attempts:
                comparability = {"comparable": False, "reason": "no_attempts"}
            elif len(attempts) < 2:
                comparability = {"comparable": False, "reason": "fewer_than_two_attempts"}
            elif len(groups) > 1:
                comparability = {"comparable": False, "reason": "different_execution_packet"}
            else:
                comparability = {"comparable": True, "reason": None}

            failures = sorted(a["attempt_id"] for a in attempts
                              if a["status"] in ("failed", "unknown", "interrupted", "cancelled"))
            selections=[]
            for oid,rid,seq in self._current_heads("selection","current",as_of):
                body=self._payload("selection",oid,rid) or {}
                aid=(body.get("attempt_ref") or {}).get("object_id")
                if any(attempt["attempt_id"]==aid for attempt in attempts) and body.get("purpose")=="delivery":
                    selections.append((seq,body))
            selection=max(selections,key=lambda item:item[0])[1] if selections else None
            selected=next((a for a in attempts if selection and a["attempt_id"]==selection["attempt_ref"]["object_id"]),None)
            cost_completeness = (COMPLETE if reported and not unknown and not dedup
                                 else INCOMPLETE)
            data = {
                "task_ref": task.to_dict(),
                "formula_version": "p06-attempt-cost-1.0.0",
                "attempts": attempts,
                "comparable_groups": {k: sorted(v) for k, v in sorted(groups.items())},
                "comparability": comparability,
                "failures_retained": failures,
                "cost": {"reported": reported, "unknown": unknown, "deduplicated": dedup,
                         "total": total, "completeness": cost_completeness,
                         "missing_usage_is_not_zero": True},
                "selected": ({"attempt_id": selected["attempt_id"],
                              "basis": "explicit_selection",
                              "reason": selection["reason"],
                              "cost": selected.get("cost")} if selected else None),
            }
            return env.finalize("attempts.compare", data, as_of_seq=as_of)
        return {}  # pragma: no cover

    def _describe_attempt(self, attempt_id: str, packet_id: str | None,
                          payload: dict[str, Any],
                          revisions: list[tuple[str, str, dict[str, Any], int, int]],
                          as_of: int) -> dict[str, Any]:
        strategy_id = None
        mode = payload.get("mode")
        handle = payload.get("execution_handle_id")
        cost: str | None = None
        usage_key: str | None = None
        for _, _, rev_payload, _, _ in revisions:
            strategy_id = strategy_id or rev_payload.get("strategy_id")
            mode = mode or rev_payload.get("mode")
            handle = handle or rev_payload.get("execution_handle_id")
            for key in ("usage", "cost", "amount", "token_usage"):
                value = rev_payload.get(key)
                if isinstance(value, dict) and isinstance(value.get("amount"), str):
                    cost = value["amount"]
                elif isinstance(value, str) and value.isdigit():
                    cost = value
                elif isinstance(value, bool):
                    pass
                elif isinstance(value, int) and value >= 0:
                    cost = str(value)
            for key in ("source_use_key", "source_outcome_key", "source_seq", "effect_id"):
                if rev_payload.get(key):
                    usage_key = f"{key}:{rev_payload[key]}"
        verification = self.store.conn.execute(
            "SELECT result FROM verification_index WHERE attempt_id=?"
            " ORDER BY report_ref DESC LIMIT 1", (attempt_id,)).fetchone()
        if verification is None:
            for oid, rid, _, _, _ in self._revisions_at("verification", as_of):
                rev_payload = self._payload("verification", oid, rid) or {}
                aref = rev_payload.get("attempt_ref")
                if isinstance(aref, dict) and aref.get("object_id") == attempt_id:
                    verification = (rev_payload.get("result"),)
        return {"attempt_id": attempt_id, "packet_id": packet_id, "strategy_id": strategy_id,
                "status": payload.get("status"), "mode": mode,
                "execution_handle_id": handle, "exit_code": payload.get("exit_code"),
                "verification_result": verification[0] if verification else None,
                "revision_count": len(revisions),
                "_cost": cost, "_usage_key": usage_key}

    # approvals.queue ------------------------------------------------------
    def approvals_queue(self, status: str | None = None, *, as_of_seq: str | int | None = None,
                        page_token: str | None = None, limit: int = 50) -> dict[str, Any]:
        if status is not None and status not in _APPROVAL_STATUSES:
            raise KernelError(invalid_input(f"unknown approval status {status!r}"))
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise KernelError(invalid_input("limit must be between 1 and 1000"))
        env = self._envelope()
        with self._read_tx():
            if page_token:
                token_as_of,_=decode_page_token(page_token,query="approvals.queue",
                    project_id=self.store.project_id,store_id=self.store.store_id,
                    filter_hash=self._filter_hash("approvals.queue",{"status": status, "limit": limit}),
                    requested_as_of=int(as_of_seq) if as_of_seq is not None else None)
                as_of_seq=token_as_of
            as_of = env.resolve_as_of(as_of_seq)
            queue: list[dict[str, Any]] = []
            for approval_id, revision_id, commit_seq in self._current_heads(
                    "approval", "current", as_of):
                payload = self._payload("approval", approval_id, revision_id) or {}
                head_row=self.store.conn.execute("SELECT head_version FROM head_history WHERE project_id=? AND type='approval' AND object_id=? AND pointer_name='current' AND commit_seq<=? ORDER BY commit_seq DESC LIMIT 1",(self.store.project_id,approval_id,as_of)).fetchone()
                entry = {
                    "approval_id": approval_id,
                    "snapshot_id": payload.get("snapshot_id"),
                    "snapshot_digest": (payload.get("snapshot_digest") or payload.get("digest")),
                    "status": payload.get("status"),
                    "head_version": str(head_row[0]) if head_row else "0",
                    "expires_at": payload.get("expires_at"),
                    "commit_seq": str(commit_seq),
                    "_sort": f"{str(payload.get('snapshot_id') or ''):>32}:{approval_id}",
                }
                if status is not None and entry["status"] != status:
                    continue
                queue.append(entry)
            queue.sort(key=lambda e: str(e["_sort"]), reverse=True)
            page, next_token, as_of = self._page(
                queue, query="approvals.queue", filters={"status": status, "limit": limit},
                as_of=as_of, limit=limit, page_token=page_token)
            for entry in page:
                entry.pop("_sort", None)
            data = {"queue": page, "count": len(page), "status_filter": status,
                    "pending_count": sum(1 for e in queue if e["status"] == "pending")}
            return env.finalize("approvals.queue", data, as_of_seq=as_of,
                                next_page_token=next_token)
        return {}  # pragma: no cover

    # environment.report ---------------------------------------------------
    def environment_report(self, task_ref: dict[str, Any], *,
                           as_of_seq: str | int | None = None) -> dict[str, Any]:
        task = ObjectRef.from_dict(task_ref)
        if task.project_id != self.store.project_id:
            raise KernelError(invalid_input("task_ref belongs to another project"))
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            snapshot: dict[str, Any] | None = None
            snapshot_seq = -1
            for object_type in ("environment_snapshot", "environment_probe"):
                for _, _, payload, cseq, _ in self._revisions_at(object_type, as_of):
                    tref = payload.get("task_ref")
                    if ((isinstance(tref, dict) and tref.get("object_id") == task.object_id)
                            or payload.get("task_id") == task.object_id):
                        if cseq >= snapshot_seq:
                            snapshot, snapshot_seq = payload, cseq
            if snapshot is None:
                # No probe recorded yet: absence of data, never merged with failure.
                data = {"task_ref": task.to_dict(), "data_state": "no_data", "snapshot": None,
                        "facts": [], "satisfied": [], "missing": [], "unknown": [],
                        "too_old": [], "not_checked": [], "checked_at": None,
                        "freshness_state": "unknown"}
                return env.finalize("environment.report", data, as_of_seq=as_of)
            failed = (snapshot.get("state") in ("failed", "error")
                      or bool(snapshot.get("probe_error")))
            facts = snapshot.get("requirements") or snapshot.get("facts") or []
            buckets: dict[str, list[dict[str, Any]]] = {
                "satisfied": [], "missing": [], "unknown": [], "too_old": [], "not_checked": []}
            normalized: list[dict[str, Any]] = []
            for fact in facts:
                entry = _normalize_fact(fact)
                normalized.append(entry)
                buckets[entry["state"]].append(entry)
            checked_at = snapshot.get("checked_at") or snapshot.get("probed_at")
            extra_gaps: list[Any] = []
            if failed:
                data_state = "source_failed"
                extra_gaps.append({"reason": "environment_probe_failed",
                                   "detail": snapshot.get("probe_error") or snapshot.get("error")
                                   or "probe failed without requirement facts"})
            else:
                data_state = "ok" if facts else "no_data"
            data = {"task_ref": task.to_dict(), "data_state": data_state, "snapshot": snapshot,
                    "facts": normalized, "satisfied": buckets["satisfied"],
                    "missing": buckets["missing"], "unknown": buckets["unknown"],
                    "too_old": buckets["too_old"], "not_checked": buckets["not_checked"],
                    "checked_at": checked_at,
                    "freshness_state": "fresh" if (checked_at and not failed) else "unknown"}
            return env.finalize("environment.report", data, as_of_seq=as_of,
                                extra_gaps=extra_gaps)
        return {}  # pragma: no cover

    # archive.status -------------------------------------------------------
    def archive_status(self, manifest_ref: dict[str, Any] | None = None, *,
                       as_of_seq: str | int | None = None) -> dict[str, Any]:
        manifest_id = None
        requested = None
        if manifest_ref is not None:
            requested = ObjectRef.from_dict(manifest_ref)
            if requested.project_id != self.store.project_id or requested.object_type != "archive_manifest":
                raise KernelError(invalid_input("manifest must belong to this project's archive"))
            manifest_id = requested.object_id
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            historical = as_of < env.head_seq()
            requested_row = self.store.get_revision(requested) if requested is not None else None
            if requested is not None and (requested_row is None or requested_row["commit_seq"] > as_of):
                raise KernelError(reference_not_found("archive manifest revision is not present at the requested watermark"))
            manifests = {}
            required_sinks_by_manifest = {}
            if requested_row is not None:
                required_sinks_by_manifest[manifest_id] = requested_row["payload"].get("required_sinks", [])
                manifests[manifest_id] = {"manifest_id": manifest_id,
                    "commit_seq": str(requested_row["commit_seq"]), "digest": requested_row["digest"],
                    "manifest_ref": requested.to_dict()}
            for oid, rid, seq in self._current_heads("archive_manifest", "current", as_of):
                if requested is not None:
                    continue
                body = self._payload("archive_manifest", oid, rid) or {}
                required_sinks_by_manifest[oid] = body.get("required_sinks", [])
                manifests[oid] = {"manifest_id": oid, "commit_seq": str(seq),
                                  "digest": sha256_digest(body),
                                  "manifest_ref": ObjectRef(self.store.project_id, "archive_manifest", oid, rid).to_dict()}
            for oid, digest, seq in self.store.conn.execute(
                    "SELECT manifest_id,digest,commit_seq FROM archive_manifest"
                    " WHERE project_id=? AND commit_seq<=?", (self.store.project_id, as_of)):
                if manifest_id is None or manifest_id == oid:
                    manifests.setdefault(oid, {"manifest_id": oid, "digest": digest, "commit_seq": str(seq)})
            sinks = {}
            sink_sequences = {}
            deliveries = []
            archive_states = []
            def save_sink(mid, receipt, commit_seq=0):
                if manifest_id is not None and mid != manifest_id:
                    return
                expected_digest = manifests.get(mid, {}).get("digest")
                if requested is not None and receipt.get("digest") is not None and receipt["digest"] != expected_digest:
                    return
                if receipt.get("state") == "succeeded" and (expected_digest is None
                        or receipt.get("digest") != expected_digest or receipt.get("verified") is not True):
                    receipt = {**receipt, "state": "unknown", "reported_state": "succeeded",
                               "error": "archive receipt verification unavailable"}
                sid = receipt.get("sink_id")
                if mid and sid and commit_seq >= sink_sequences.get((mid, sid), -1):
                    sinks[(mid, sid)] = {**receipt, "manifest_id": mid}
                    sink_sequences[(mid, sid)] = commit_seq
            for oid, rid, seq in self._current_heads("delivery", "current", as_of):
                body = self._payload("delivery", oid, rid) or {}
                receipt = body.get("sink_receipt")
                if requested is None or (manifest_id == oid and isinstance(receipt, dict)
                        and receipt.get("digest") == requested_row["digest"]):
                    deliveries.append({"operation_id": oid, "status": body.get("status"),
                                       "sink_receipt": body.get("sink_receipt"), "commit_seq": str(seq)})
                if isinstance(body.get("sink_receipt"), dict):
                    save_sink(body["sink_receipt"].get("manifest_id") or oid, body["sink_receipt"], seq)
            for oid, rid, seq in self._current_heads("archive_status", "current", as_of):
                body = self._payload("archive_status", oid, rid) or {}
                mid = (body.get("manifest_ref") or {}).get("object_id")
                if requested is not None and body.get("manifest_ref") != requested.to_dict():
                    continue
                archive_states.append({**body, "revision_id": rid, "commit_seq": str(seq)})
                for sid, state in body.get("sink_states", {}).items():
                    save_sink(mid, {**body.get("receipts", {}).get(sid, {}), "sink_id": sid, "state": state}, seq)
                for sid in body.get("required_sinks", []):
                    if (mid, sid) not in sinks:
                        save_sink(mid, {"sink_id": sid, "state": "pending"}, seq)
            for oid, rid, seq in self._current_heads("evidence_operation", "current", as_of):
                body = self._payload("evidence_operation", oid, rid) or {}
                if body.get("command", "").startswith("archive.") and isinstance(body.get("sink_receipt"), dict):
                    if requested is not None and body.get("payload", {}).get("manifest_ref") != requested.to_dict():
                        continue
                    mid = (body.get("payload", {}).get("manifest_ref") or {}).get("object_id")
                    save_sink(mid, body["sink_receipt"], seq)
            required_missing = []
            for mid, sid, state, digest, error in self.store.conn.execute(
                    "SELECT manifest_id,sink,state,digest,error FROM sink_receipt WHERE project_id=?",
                    (self.store.project_id,)):
                if manifest_id is not None and manifest_id != mid:
                    continue
                if (mid, sid) in sinks:
                    continue
                if historical:
                    if "sink_history_unavailable" not in required_missing:
                        required_missing.append("sink_history_unavailable")
                else:
                    save_sink(mid, {"sink_id": sid, "state": state, "digest": digest, "error": error,
                                    "history_state": "unavailable"})
            for mid, required in required_sinks_by_manifest.items():
                for sid in required:
                    if (mid, sid) not in sinks:
                        save_sink(mid, {"sink_id": sid, "state": "pending"})
            partial = [sink for sink in sinks.values() if sink.get("state") != "succeeded"]
            gaps = [{"reason": "archive_partial", "manifest_id": sink["manifest_id"],
                     "sink_id": sink["sink_id"], "error_code": "ARCHIVE_PARTIAL"} for sink in partial]
            source_partial = [state for state in archive_states if state.get("source_flushed") is not True]
            gaps.extend({"reason": "archive_source_incomplete", "manifest_id": state["manifest_ref"]["object_id"],
                         "source_flush_basis": state.get("source_flush_basis", "unavailable"),
                         "error_code": "ARCHIVE_PARTIAL"} for state in source_partial)
            meta = self.store.get_project_meta() or {}
            data = {"manifest_id": manifest_id, "manifests": list(manifests.values()),
                    "sinks": list(sinks.values()), "archive_states": archive_states,
                    "main_store": {"store_id": self.store.store_id, "project_id": self.store.project_id,
                                   "schema_version": meta.get("schema_version"), "as_of_seq": str(as_of)},
                    "session_flush": {"state": "not_configured",
                                      "detail": "no host flush proof persisted; local observations do not prove host flush"},
                    "deliveries": deliveries, "partial": bool(partial) or bool(source_partial) or bool(required_missing),
                    "errors": [{"code": "ARCHIVE_PARTIAL", "manifest_id": sink["manifest_id"],
                                "sink_id": sink["sink_id"], "error": sink.get("error")} for sink in partial]}
            return env.finalize("archive.status", data, as_of_seq=as_of,
                                extra_gaps=gaps, required_missing=required_missing)

    # projection rebuild (read-only safe) ----------------------------------
    def rebuild_read_model(self, projection: str = "all", *,
                           as_of_seq: str | int | None = None) -> dict[str, Any]:
        """Recompute the read models from the immutable ledger at one as_of.

        Read-only safety: nothing is written; the rebuild only reads revision /
        entity_head / head_history. Consistency basis: the ledger is append-only
        (revision and head_history rows are never updated in place) and the
        recomputation is a pure function of (ledger rows, as_of), so a rebuild at
        a fixed as_of reproduces the live read model exactly. Persisting a
        projection_checkpoint row needs a P01 DDL migration (ChangeRequest in
        docs/handoffs/P06.md); until then ``persisted`` stays false so a caller
        cannot mistake an in-memory rebuild for a durable projection.
        """
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            overview = self._recompute_projection("project.overview", as_of)
            coverage = self._recompute_projection("requirements.coverage", as_of)
            mismatches = self._verify_head_consistency(as_of)
            digest = sha256_digest({"as_of_seq": str(as_of), "overview": overview,
                                    "coverage": coverage})
            data = {"projection_name": projection, "as_of_seq": str(as_of),
                    "projection_version": PROJECTION_VERSION,
                    "consistent": not mismatches, "mismatches": mismatches,
                    "rebuilt": {"project.overview": overview,
                                "requirements.coverage": coverage},
                    "digest": digest, "persisted": False,
                    "requires_ddl": "projection_checkpoint(projection_name,as_of_seq,"
                                    "projection_version,status,error)",
                    "consistency_basis": "append-only revision/head_history ledger;"
                                         " rebuild is a pure function of (ledger, as_of)"}
            return env.finalize("projection.rebuild", data, as_of_seq=as_of)
        return {}  # pragma: no cover

    def _recompute_projection(self, name: str, as_of: int) -> dict[str, Any]:
        if name == "project.overview":
            counts = {r[0]: int(r[1]) for r in self.store.conn.execute(
                "SELECT type, COUNT(*) FROM entity WHERE created_seq<=? GROUP BY type",
                (as_of,))}
            return {"object_counts": counts, "store_id": self.store.store_id}
        reqs = sorted(oid for oid, _, _ in self._current_heads("requirement", "current", as_of))
        return {"requirement_ids": reqs, "as_of_seq": str(as_of)}

    def _verify_head_consistency(self, as_of: int) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        for otype, oid, pointer, revision_id, _head_version, updated_seq in \
                self.store.conn.execute(
                    "SELECT type, object_id, pointer_name, revision_id, head_version,"
                    " updated_seq FROM entity_head WHERE updated_seq<=?",
                    (as_of,)).fetchall():
            published = self.store.head_as_of(otype, oid, pointer, int(updated_seq))
            if published != revision_id:
                mismatches.append({"type": otype, "object_id": oid, "pointer_name": pointer,
                                   "reason": "head_history_mismatch",
                                   "head_revision": revision_id, "history_revision": published})
            exists = self.store.conn.execute(
                "SELECT 1 FROM revision WHERE project_id=? AND type=? AND object_id=?"
                " AND revision_id=?",
                (self.store.project_id, otype, oid, revision_id)).fetchone()
            if exists is None:
                mismatches.append({"type": otype, "object_id": oid, "pointer_name": pointer,
                                   "reason": "head_revision_missing",
                                   "head_revision": revision_id})
        return mismatches

    # list_revisions / latest_revisions (CR-3 typed read API) --------------
    def list_revisions(self, object_type: str, after_seq: int = 0, *,
                       as_of_seq: str | int | None = None) -> list[dict[str, Any]]:
        """All revisions of ``object_type`` in commit order, scoped to this project.

        ``commit_seq > after_seq`` and (optionally) ``commit_seq <= as_of_seq``.
        """
        bound = self._envelope().resolve_as_of(as_of_seq)
        rows = self.store.conn.execute(
            "SELECT object_id, revision_id, payload_json, digest, commit_seq FROM revision"
            " WHERE project_id=? AND type=? AND commit_seq > ? AND commit_seq <= ?"
            " ORDER BY commit_seq",
            (self.store.project_id, object_type, after_seq, bound)).fetchall()
        return [{"object_id": r[0], "revision_id": r[1], "payload": json.loads(r[2]),
                 "digest": r[3], "commit_seq": int(r[4])} for r in rows]

    def latest_revisions(self, object_type: str, *,
                         as_of_seq: str | int | None = None) -> list[dict[str, Any]]:
        """Latest revision per object at ``as_of_seq`` (max ordinal), project-scoped.

        Truncates at the as_of watermark and returns exactly one row per object,
        ordered by ``object_id`` so callers get a stable typed read model.
        """
        env = self._envelope()
        with self._read_tx():
            as_of = env.resolve_as_of(as_of_seq)
            rows = self.store.conn.execute(
                "SELECT r.object_id, r.revision_id, r.payload_json, r.digest, r.commit_seq,"
                " r.ordinal FROM revision r"
                " JOIN (SELECT object_id, MAX(ordinal) AS mo FROM revision"
                "        WHERE project_id=? AND type=? AND commit_seq<=?"
                "        GROUP BY object_id) m"
                "   ON m.object_id=r.object_id AND m.mo=r.ordinal"
                " WHERE r.project_id=? AND r.type=?"
                " ORDER BY r.object_id",
                (self.store.project_id, object_type, as_of,
                 self.store.project_id, object_type)).fetchall()
            return [{"object_id": r[0], "revision_id": r[1], "payload": json.loads(r[2]),
                     "digest": r[3], "commit_seq": int(r[4]), "ordinal": int(r[5]),
                     "as_of_seq": str(as_of)} for r in rows]
        return []  # pragma: no cover
