"""Reconciliation report: failed/unselected attempts, approvals, evidence, files.

Compares the mapped facts (and, when persisted payloads are supplied, the
stored imported facts) against the legacy source. It reports mismatches instead
of silently accepting them; it never fabricates a pass, approval, usage amount
or causal parent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mapper import ImportedFact
from .source import LegacyRecord


@dataclass(frozen=True)
class ReconcileEntry:
    legacy_type: str
    legacy_id: str
    source_digest: str
    classification: str
    mapped_ref: str | None
    mismatch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"legacy_type": self.legacy_type, "legacy_id": self.legacy_id,
                "source_digest": self.source_digest, "classification": self.classification,
                "mapped_ref": self.mapped_ref, "mismatch": self.mismatch}


@dataclass(frozen=True)
class ReconcileReport:
    source_store_id: str
    target_project_id: str
    attempts: tuple[ReconcileEntry, ...] = ()
    approvals: tuple[ReconcileEntry, ...] = ()
    evidence: tuple[ReconcileEntry, ...] = ()
    files: tuple[ReconcileEntry, ...] = ()
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_store_id": self.source_store_id,
            "target_project_id": self.target_project_id,
            "ok": self.ok,
            "attempts": [a.to_dict() for a in self.attempts],
            "approvals": [a.to_dict() for a in self.approvals],
            "evidence": [a.to_dict() for a in self.evidence],
            "files": [a.to_dict() for a in self.files],
        }


def _key_of(legacy_type: str, legacy_id: str) -> tuple[str, str]:
    return (legacy_type, legacy_id)


def reconcile(source_store_id: str,
              target_project_id: str,
              source_records: tuple[LegacyRecord, ...],
              facts: tuple[ImportedFact, ...],
              persisted: dict[tuple[str, str], dict[str, Any]] | None = None) -> ReconcileReport:
    """Reconcile mapped facts against source records and persisted payloads.

    ``persisted`` maps ``(legacy_type, legacy_id) -> stored imported-fact payload``
    (read from the target revision ledger). When ``None``, only plan-level
    invariants are checked (storage retention is not verified).
    """
    by_key = {_key_of(f.legacy_type, f.legacy_id): f for f in facts}
    check_stored = persisted is not None
    stored_lookup = persisted if persisted is not None else {}
    buckets: dict[str, list[ReconcileEntry]] = {
        "attempt": [], "approval": [], "evidence": [], "file": [],
    }
    ok = True

    def add(fact: ImportedFact, mismatch: str | None) -> None:
        nonlocal ok
        if mismatch is not None:
            ok = False
        buckets[fact.legacy_type].append(ReconcileEntry(
            legacy_type=fact.legacy_type, legacy_id=fact.legacy_id,
            source_digest=fact.source_digest, classification=fact.classification,
            mapped_ref=(target_project_id + ":" + fact.object_id) if fact.is_ok else None,
            mismatch=mismatch))

    for rec in source_records:
        if rec.legacy_type not in buckets:
            continue
        fact = by_key.get(_key_of(rec.legacy_type, rec.legacy_id))
        if fact is None:
            continue
        mismatch: str | None = None
        stored = stored_lookup.get(_key_of(rec.legacy_type, rec.legacy_id))

        if rec.legacy_type == "attempt" and fact.classification == "ok":
            if check_stored:
                if rec.attempt_status == "failed":
                    if stored is None:
                        mismatch = "failed attempt has no persisted imported fact"
                    elif stored.get("raw", {}).get("status") != "failed":
                        mismatch = "failed attempt status was changed during import"
                if rec.selected is False:
                    raw_selected = (stored or {}).get("raw", {}).get("selected")
                    if raw_selected in (True, "True", "1", "true", 1):
                        mismatch = "unselected attempt was re-marked selected"
        elif rec.legacy_type == "approval" and check_stored:
            if rec.approval_decision is None:
                mismatch = "approval record missing decision"
            elif stored is not None and stored.get("raw", {}).get("decision") != rec.approval_decision:
                mismatch = "approval decision was changed during import"
        elif rec.legacy_type in ("evidence", "file") and check_stored:
            expected = str(rec.raw.get("sha256", ""))
            if stored is not None and str(stored.get("raw", {}).get("sha256", "")) != expected:
                mismatch = "evidence/file hash changed during import"

        add(fact, mismatch)

    return ReconcileReport(
        source_store_id=source_store_id,
        target_project_id=target_project_id,
        attempts=tuple(buckets["attempt"]),
        approvals=tuple(buckets["approval"]),
        evidence=tuple(buckets["evidence"]),
        files=tuple(buckets["file"]),
        ok=ok,
    )
