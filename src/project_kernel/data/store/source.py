"""Source event ingest with a contiguous watermark.

Identity = (host_id, origin_session_id, log_generation, source_seq). Same key +
same hash is a duplicate; same key + different hash is SOURCE_CONFLICT (original
is kept). Out-of-order events are stored but the cursor only advances over
consecutive persisted sequences - it never takes MAX(source_seq).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from ...contracts import sha256_digest
from ...contracts.dto import SourceKey
from ...contracts.errors import KernelError, source_conflict


def bounded_missing_sequences(sequences: Iterable[int], *, limit: int = 100) -> dict[str, Any]:
    """Summarize absent positive sequence numbers without walking the high-water span."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    present = sorted({int(seq) for seq in sequences if int(seq) > 0})
    missing: list[int] = []
    ranges: list[dict[str, str]] = []
    missing_count = 0
    next_missing = None
    cursor = 1
    for seq in present:
        if seq > cursor:
            start, end = cursor, seq - 1
            span = end - start + 1
            missing_count += span
            if next_missing is None:
                next_missing = start
            if len(missing) < limit:
                missing.extend(range(start, min(end, start + limit - len(missing) - 1) + 1))
            if len(ranges) < limit:
                ranges.append({"first": str(start), "last": str(end)})
        cursor = seq + 1
    return {"missing": missing, "missing_count": str(missing_count), "ranges": ranges,
            "next_missing_seq": str(next_missing) if next_missing is not None else None,
            "truncated": missing_count > len(missing)}


class SourceIngest:
    def __init__(self, conn: sqlite3.Connection, commit_seq: int):
        self.conn = conn
        self.commit_seq = commit_seq

    def ingest(self, stream_key: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            raise ValueError("source ingest requires at least one event")
        accepted: list[str] = []
        duplicates: list[str] = []
        conflicts: list[str] = []
        stream_identity = None
        for ev in events:
            key = SourceKey(ev["host_id"], ev["origin_session_id"], ev["log_generation"],
                            ev["source_seq"])
            identity = (key.host_id, key.origin_session_id, key.log_generation)
            if stream_identity is not None and identity != stream_identity:
                raise ValueError("one source.ingest batch must contain a single source stream")
            stream_identity = identity
            body = ev.get("body")
            payload = {"source_key": key.to_dict(), "body": body}
            payload_hash = sha256_digest(payload)
            existing = self.conn.execute(
                "SELECT payload_hash FROM source_event"
                " WHERE host_id=? AND origin_session_id=? AND log_generation=? AND source_seq=?",
                (key.host_id, key.origin_session_id, key.log_generation, key.source_seq),
            ).fetchone()
            if existing is not None:
                if existing[0] == payload_hash:
                    duplicates.append(key.source_seq)
                    continue
                conflicts.append(key.source_seq)
                raise KernelError(source_conflict(
                    f"source conflict at {stream_key}#{key.source_seq}"))
            self.conn.execute(
                "INSERT INTO source_event (host_id, origin_session_id, log_generation,"
                " source_seq, payload_hash, schema_version, body, commit_seq, completeness)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (key.host_id, key.origin_session_id, key.log_generation, key.source_seq,
                 payload_hash, ev.get("schema_version", "1.0.0"),
                 json.dumps(body, ensure_ascii=False) if body is not None else None,
                 self.commit_seq, ev.get("completeness", "complete")),
            )
            accepted.append(key.source_seq)

        canonical_key = self.canonical_stream_key(*stream_identity)
        self._advance_cursor(canonical_key, *stream_identity)
        return {"accepted": accepted, "duplicates": duplicates, "conflicts": conflicts,
                "contiguous_seq": self._contiguous(canonical_key)}

    @staticmethod
    def canonical_stream_key(host_id: str, origin_session_id: str,
                             log_generation: str) -> str:
        return json.dumps([host_id, origin_session_id, log_generation],
                          ensure_ascii=False, separators=(",", ":"))

    def _advance_cursor(self, stream_key: str, host_id: str, origin_session_id: str,
                        log_generation: str) -> None:
        rows = self.conn.execute(
            "SELECT source_seq FROM source_event WHERE host_id=? AND origin_session_id=?"
            " AND log_generation=?",
            (host_id, origin_session_id, log_generation),
        ).fetchall()
        seqs = sorted(int(r[0]) for r in rows)
        contiguous = 0
        for s in seqs:
            if s == contiguous + 1:
                contiguous = s
            elif s <= contiguous:
                continue
            else:
                break
        gap_summary = bounded_missing_sequences(seqs)
        gaps = gap_summary["missing"]
        self.conn.execute(
            "INSERT INTO source_cursor (source_stream_key, contiguous_seq, seen_high_water,"
            " gaps_json, status, updated_seq)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(source_stream_key) DO UPDATE SET contiguous_seq=excluded.contiguous_seq,"
            " seen_high_water=excluded.seen_high_water, gaps_json=excluded.gaps_json,"
            " status=excluded.status, updated_seq=excluded.updated_seq",
            (stream_key, str(contiguous), str(seqs[-1] if seqs else 0),
             json.dumps(gaps), "active" if not gaps else "gapped", self.commit_seq),
        )

    def _contiguous(self, stream_key: str) -> str:
        row = self.conn.execute("SELECT contiguous_seq FROM source_cursor WHERE source_stream_key=?",
                                (stream_key,)).fetchone()
        return row[0] if row else "0"
