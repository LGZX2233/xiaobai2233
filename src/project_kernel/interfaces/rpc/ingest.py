"""``source.ingest`` envelope -> typed request mapping (design 04 §4/§9, 02 source).

This module is a *protocol boundary* adapter: it turns a schema-validated
envelope into the typed arguments the owner of the business behaviour (P01
source store / P03 ingest / P04 settle; design 09 ``SourcePort.ingest``) expects.
It creates no business state and invents no status: cursor gaps, duplicates,
SOURCE_CONFLICT and forked lineage stay with the owner.

Rejected here are only envelope-level inconsistencies a client can fix without
any business knowledge: a duplicated ``source_seq`` inside one batch, events
outside the declared ``observed_range``, or a range declared complete
(``truncated=false``) while events are missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Mapping, Sequence

from ...contracts.errors import KernelError, invalid_input, unsupported_command
from .commands import compute_input_hash, receipt_domain_for
from .invocation import current_machine_context

SOURCE_INGEST_COMMAND = "source.ingest"


@dataclass(frozen=True)
class SourceStreamKey:
    """host/origin_session/log_generation form the stream identity (02 §source)."""

    host_id: str
    origin_session_id: str
    log_generation: str

    def canonical(self) -> str:
        return json.dumps([self.host_id, self.origin_session_id, self.log_generation],
                          ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class SourceEvent:
    source_seq: str
    payload_hash: str
    schema_version: str
    payload_artifact_ref: Mapping[str, Any]
    evidence_mode: str
    inherited_from: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_seq": self.source_seq,
            "payload_hash": self.payload_hash,
            "schema_version": self.schema_version,
            "payload_artifact_ref": dict(self.payload_artifact_ref),
            "evidence_mode": self.evidence_mode,
        }
        if self.inherited_from is not None:
            data["inherited_from"] = dict(self.inherited_from)
        return data


@dataclass(frozen=True)
class ObservedRange:
    first: int
    last: int
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {"first": str(self.first), "last": str(self.last),
                "truncated": self.truncated}


@dataclass(frozen=True)
class SourceIngestRequest:
    """Everything a business delegate needs; the handle is never present."""

    selector: Mapping[str, Any]
    idempotency_key: str
    input_hash: str
    stream: SourceStreamKey
    events: tuple[SourceEvent, ...]
    observed_range: ObservedRange
    expected_heads: Sequence[Any] = field(default_factory=tuple)
    principal_id: str | None = None
    capabilities: frozenset[str] = frozenset()
    receipt_domain: str = "project"
    command: str = SOURCE_INGEST_COMMAND

    @property
    def stream_key(self) -> str:
        return self.stream.canonical()

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "selector": dict(self.selector),
            "idempotency_key": self.idempotency_key,
            "input_hash": self.input_hash,
            "receipt_domain": self.receipt_domain,
            "source_stream": {
                "host_id": self.stream.host_id,
                "origin_session_id": self.stream.origin_session_id,
                "log_generation": self.stream.log_generation,
            },
            "events": [e.to_dict() for e in self.events],
            "observed_range": self.observed_range.to_dict(),
        }


def map_source_ingest(params: Mapping[str, Any], *,
                      principal_id: str | None = None,
                      capabilities: frozenset[str] = frozenset()) -> SourceIngestRequest:
    """Map validated command ``params`` to a typed source-ingest request."""
    payload = params.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise KernelError(invalid_input("source.ingest payload must be an object"))

    stream = _require_object(payload.get("source_stream"), "source_stream")
    events_raw = payload.get("events")
    if not isinstance(events_raw, list) or not events_raw:
        raise KernelError(invalid_input("source.ingest requires at least one event"))
    range_raw = _require_object(payload.get("observed_range"), "observed_range")

    observed = ObservedRange(
        first=_seq_int(range_raw.get("first"), "observed_range.first"),
        last=_seq_int(range_raw.get("last"), "observed_range.last"),
        truncated=bool(range_raw.get("truncated")),
    )
    if observed.first > observed.last:
        raise KernelError(invalid_input(
            "observed_range.first must not exceed observed_range.last"))

    events: list[SourceEvent] = []
    seen: set[str] = set()
    for raw in events_raw:
        event = _require_object(raw, "events[]")
        seq = event.get("source_seq")
        seq_int = _seq_int(seq, "events[].source_seq")
        if seq_int in seen:
            raise KernelError(invalid_input(f"duplicate source_seq {seq!r} in one batch"))
        seen.add(seq_int)
        if seq_int < observed.first or seq_int > observed.last:
            raise KernelError(invalid_input(
                f"source_seq {seq!r} is outside the declared observed_range"))
        inherited = event.get("inherited_from")
        events.append(SourceEvent(
            source_seq=str(seq),
            payload_hash=event.get("payload_hash"),
            schema_version=event.get("schema_version"),
            payload_artifact_ref=_require_object(
                event.get("payload_artifact_ref"), "events[].payload_artifact_ref"),
            evidence_mode=event.get("evidence_mode"),
            inherited_from=_require_object(inherited, "events[].inherited_from")
            if inherited is not None else None,
        ))

    if not observed.truncated:
        expected = observed.last - observed.first + 1
        if len(seen) != expected:
            raise KernelError(invalid_input(
                "observed_range is declared complete but the batch does not carry "
                f"every sequence ({len(seen)} of {expected})"))

    selector = params.get("selector") or {}
    expected_heads = list(params.get("expected_heads") or [])
    return SourceIngestRequest(
        selector=dict(selector),
        idempotency_key=params["idempotency_key"],
        input_hash=compute_input_hash(SOURCE_INGEST_COMMAND, selector,
                                      expected_heads, payload),
        stream=SourceStreamKey(
            host_id=stream["host_id"],
            origin_session_id=stream["origin_session_id"],
            log_generation=stream["log_generation"],
        ),
        events=tuple(events),
        observed_range=observed,
        expected_heads=tuple(expected_heads),
        principal_id=principal_id,
        capabilities=frozenset(capabilities or ()),
        receipt_domain=receipt_domain_for(SOURCE_INGEST_COMMAND),
    )


class SourceIngestBridge:
    """Dispatch ``source.ingest`` to an injected business delegate.

    ``delegate`` receives the typed request (never the raw envelope) and returns
    a ``CommandReceipt``-shaped object or mapping; the bridge only shapes it into
    the RPC result and never synthesises a business status. The trusted principal
    comes from the resolved invocation context, never from the wire params.
    """

    def __init__(self, delegate: Callable[[SourceIngestRequest], Any]) -> None:
        if delegate is None:
            raise ValueError("source.ingest requires a business delegate")
        self._delegate = delegate

    def handle(self, command: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if command != SOURCE_INGEST_COMMAND:
            raise KernelError(unsupported_command(
                f"SourceIngestBridge only serves {SOURCE_INGEST_COMMAND}"))
        context = current_machine_context()
        request = map_source_ingest(
            params,
            principal_id=context.principal_id if context else None,
            capabilities=context.capabilities if context else frozenset(),
        )
        receipt = self._delegate(request)
        return {"receipt": _receipt_dict(receipt)}


def _receipt_dict(value: Any) -> dict[str, Any]:
    if value is None:
        raise KernelError(invalid_input("source.ingest delegate returned no receipt"))
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise KernelError(invalid_input(
        "source.ingest delegate receipt must be a mapping or CommandReceipt"))


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if value is None or not isinstance(value, Mapping):
        raise KernelError(invalid_input(f"{label} must be an object"))
    return dict(value)


def _seq_int(value: Any, label: str) -> int:
    if not isinstance(value, str) or not value.isdigit():
        raise KernelError(invalid_input(f"{label} must be a decimal string"))
    if len(value) > 1 and value[0] == "0":
        raise KernelError(invalid_input(f"{label} must not have leading zeros"))
    return int(value)
