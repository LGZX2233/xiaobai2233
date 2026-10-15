"""Query envelope: as_of resolution, source watermarks, freshness/completeness
and opaque pagination tokens.

Design basis (02 §3/§5, 04 §3/§5):

* as_of_seq is the committed project transaction watermark at first-page time.
  Ledger reads are bounded by ``commit_seq <= as_of`` so later pages are stable
  even while writers advance the head.
* ``project as_of`` does not mean the host has collected every source event, so
  every envelope carries source_watermarks/freshness/completeness/gaps.
* "no data" (no stream registered yet) and "data source failed" (cursor row
  marked unavailable, or a read error) are never merged: the former is
  ``no_data``/``complete``, the latter is ``unavailable``/``unknown``.
* Page tokens use a public corruption checksum and are bound to
  project + store + query + filter + as_of + last sort key + protocol version,
  so a token cannot be replayed for a different project, filter or watermark.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ...contracts.errors import KernelError, as_of_unavailable, invalid_input

PROTOCOL_VERSION = "1.0.0"
PROJECTION_VERSION = "p06-read-model-1.0.0"

# completeness
COMPLETE = "complete"
INCOMPLETE = "incomplete"
UNKNOWN = "unknown"

# source watermark data states
STATE_NO_DATA = "no_data"
STATE_OK = "ok"
STATE_GAPPED = "gapped"
STATE_UNAVAILABLE = "unavailable"

_TOKEN_DOMAIN = "p06-page-token/v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _token_signature(body: str) -> str:
    return hashlib.sha256(f"{_TOKEN_DOMAIN}|{body}".encode("utf-8")).hexdigest()[:32]


def encode_page_token(*, query: str, project_id: str, store_id: str, filter_hash: str,
                      as_of_seq: int, last_key: str) -> str:
    payload = {"v": 1, "pv": PROTOCOL_VERSION, "q": query, "p": project_id,
               "s": store_id, "f": filter_hash, "a": str(as_of_seq), "k": last_key}
    body = _b64e(json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                            sort_keys=True).encode("utf-8"))
    return f"{body}.{_token_signature(body)}"


def decode_page_token(token: str, *, query: str, project_id: str, store_id: str,
                      filter_hash: str, requested_as_of: int | None = None) -> tuple[int, str]:
    parts = token.split(".")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise KernelError(invalid_input("malformed page token"))
    body, sig = parts
    if not hmac.compare_digest(sig, _token_signature(body)):
        raise KernelError(invalid_input("page token signature mismatch"))
    try:
        payload = json.loads(_b64d(body).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any decode failure is a bad token
        raise KernelError(invalid_input("undecodable page token")) from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise KernelError(invalid_input("unsupported page token version"))
    if payload.get("pv") != PROTOCOL_VERSION:
        raise KernelError(invalid_input("page token protocol version mismatch"))
    if payload.get("q") != query or payload.get("f") != filter_hash:
        raise KernelError(invalid_input("page token does not match this query/filter"))
    if payload.get("p") != project_id or payload.get("s") != store_id:
        raise KernelError(invalid_input("page token belongs to another project/store"))
    as_of = payload.get("a")
    if not isinstance(as_of, str) or not as_of.isdigit():
        raise KernelError(invalid_input("page token has an invalid as_of_seq"))
    if requested_as_of is not None and str(requested_as_of) != as_of:
        raise KernelError(invalid_input("as_of_seq conflicts with the page token watermark"))
    return int(as_of), str(payload.get("k", ""))


class ReadEnvelope:
    """Builds the QueryEnvelope shell for one read query on one connection."""

    def __init__(self, conn: sqlite3.Connection, project_id: str, store_id: str):
        self.conn = conn
        self.project_id = project_id
        self.store_id = store_id

    # -- watermark ------------------------------------------------------
    def head_seq(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(commit_seq), 0) FROM commit_log").fetchone()
        return int(row[0])

    def resolve_as_of(self, requested: str | int | None) -> int:
        current = self.head_seq()
        if requested is None:
            return current
        if isinstance(requested, bool) or not isinstance(requested, (str, int)):
            raise KernelError(invalid_input("as_of_seq must be a decimal string"))
        text = str(requested)
        if not text.isdigit():
            raise KernelError(invalid_input("as_of_seq must be a decimal string"))
        as_of = int(text)
        if as_of > current:
            # Never label old data as a newer watermark.
            raise KernelError(as_of_unavailable())
        return as_of

    def source_watermarks(self, as_of_seq: int | None = None, *,
                          missing_limit: int = 100) -> dict[str, Any]:
        from ..store.source import bounded_missing_sequences

        try:
            cursors = self.conn.execute(
                "SELECT source_stream_key,status,contiguous_seq,seen_high_water,gaps_json"
                " FROM source_cursor ORDER BY source_stream_key").fetchall()
            historical = as_of_seq is not None and as_of_seq < self.head_seq()
            sql = "SELECT host_id,origin_session_id,log_generation,source_seq FROM source_event"
            params = ()
            if as_of_seq is not None:
                sql += " WHERE commit_seq<=?"
                params = (as_of_seq,)
            observed = {}
            for host, session, generation, seq in self.conn.execute(sql, params):
                key = json.dumps([host, session, generation], ensure_ascii=False,
                                 separators=(",", ":"))
                observed.setdefault(key, set()).add(int(seq))
        except sqlite3.Error as exc:
            return {"streams": [], "data_state": STATE_UNAVAILABLE,
                    "error_code": "SOURCE_UNAVAILABLE", "error": str(exc), "gaps": []}
        statuses = {} if historical else {
            row[0]: row[1:] for row in cursors
            if _is_canonical_source_stream_key(row[0])
        }
        legacy_cursors = [] if historical else [row for row in cursors
            if not _is_canonical_source_stream_key(row[0])]
        streams = []
        gaps = []
        failed = False
        for key in sorted(set(observed) | set(statuses)):
            seqs = observed.get(key, set())
            summary = bounded_missing_sequences(seqs, limit=missing_limit)
            high = max(seqs, default=0)
            contiguous = (int(summary["next_missing_seq"]) - 1
                          if summary["missing_count"] != "0" else high)
            cursor = statuses.get(key)
            status = cursor[0] if cursor else ("gapped" if summary["missing_count"] != "0" else "active")
            if cursor is not None and not seqs:
                contiguous, high = int(cursor[1]), int(cursor[2])
                try:
                    sample = json.loads(cursor[3])[:missing_limit]
                except (ValueError, TypeError):
                    sample = []
                summary = {"missing": sample, "missing_count": None, "ranges": [],
                           "next_missing_seq": str(sample[0]) if sample else None,
                           "truncated": high > contiguous, "summary_basis": "cursor_only"}
            has_gap = high > contiguous or status == "gapped"
            if status not in ("active", "gapped"):
                state = STATE_UNAVAILABLE
                failed = True
            elif has_gap:
                state = STATE_GAPPED
            else:
                state = STATE_OK
            entry = {"source_stream_key": key, "contiguous_seq": str(contiguous),
                     "seen_high_water": str(high), "status": status, "state": state,
                     **summary, "lag": str(max(high - contiguous, 0))}
            streams.append(entry)
            if has_gap:
                gaps.append({"source_stream_key": key, "state": state, **summary})
        # Legacy keys were formed by joining tuple fields with ':', so they
        # cannot be mapped back to a trustworthy source identity.
        for row in legacy_cursors:
            key = "legacy:" + row[0]
            entry = {"source_stream_key": key, "contiguous_seq": "0",
                     "seen_high_water": str(row[3]), "status": "unavailable",
                     "state": STATE_UNAVAILABLE, "missing": [], "missing_count": None,
                     "ranges": [], "next_missing_seq": None,
                     "truncated": True, "summary_basis": "legacy_cursor_unknown",
                     "lag": str(row[3])}
            streams.append(entry)
            failed = True
        data_state = (STATE_UNAVAILABLE if failed else STATE_NO_DATA if not streams
                      else STATE_GAPPED if gaps else STATE_OK)
        return {"streams": streams, "data_state": data_state, "gaps": gaps,
                "error_code": None, "error": None}
    # -- envelope -------------------------------------------------------
    def finalize(self, query: str, data: dict[str, Any], *, as_of_seq: int,
                 watermarks: dict[str, Any] | None = None,
                 next_page_token: str | None = None,
                 extra_gaps: list[Any] | None = None,
                 required_missing: list[Any] | None = None,
                 legacy_keys: bool = True) -> dict[str, Any]:
        wm = watermarks if watermarks is not None else self.source_watermarks(as_of_seq)
        head = self.head_seq()
        lag = max(head - as_of_seq, 0)
        stale = lag > 0
        gaps: list[Any] = list(wm.get("gaps", []))
        if extra_gaps:
            gaps.extend(extra_gaps)
        required_missing = list(required_missing or [])

        if wm["data_state"] == STATE_UNAVAILABLE:
            completeness = UNKNOWN
        elif gaps or stale or required_missing:
            completeness = INCOMPLETE
        else:
            completeness = COMPLETE

        if wm["data_state"] == STATE_UNAVAILABLE:
            fresh_state = UNKNOWN
        elif stale or gaps:
            fresh_state = "stale"
        else:
            fresh_state = "fresh"

        freshness = {"as_of_seq": str(as_of_seq), "store_head_seq": str(head),
                     "projection_lag_seq": str(lag), "projection_stale": stale,
                     "source_state": wm["data_state"], "state": fresh_state}

        envelope: dict[str, Any] = {
            "query": query,
            "as_of_seq": str(as_of_seq),
            "projection_version": PROJECTION_VERSION,
            "computed_at": utc_now(),
            "source_watermarks": {"streams": wm["streams"], "data_state": wm["data_state"]},
            "freshness": freshness,
            "completeness": completeness,
            "gaps": gaps,
            "required_missing": required_missing,
            "next_page_token": next_page_token,
            "data": data,
        }
        if wm.get("error_code"):
            envelope["source_error"] = {"code": wm["error_code"], "message": wm.get("error")}
        if legacy_keys:
            for key, value in data.items():
                envelope.setdefault(key, value)
        return envelope


def _is_canonical_source_stream_key(value: str) -> bool:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return False
    return (isinstance(decoded, list) and len(decoded) == 3
            and all(isinstance(part, str) for part in decoded)
            and json.dumps(decoded, ensure_ascii=False, separators=(",", ":")) == value)
