"""LegacyMapper: source-key idempotent mapping with raw field retention.

The source key is ``(source_store_id, legacy_type, legacy_id)`` and maps
deterministically to a target ``object_id``. Re-running the mapper for the same
source therefore yields the same identity. The original ``raw`` payload is kept
verbatim on every mapped fact; no pass, approval, usage or causal parent is
ever invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...contracts.dto import ObjectRef
from ...contracts.digest import sha256_digest
from .source import LegacyRecord


class Classification:
    OK = "ok"
    ORPHAN = "orphan"
    UNOWNED = "unowned"
    DUPLICATE = "duplicate"
    MISSING_HISTORY = "missing_history"


ALL_CLASSIFICATIONS = (
    Classification.OK,
    Classification.ORPHAN,
    Classification.UNOWNED,
    Classification.DUPLICATE,
    Classification.MISSING_HISTORY,
)

# Legacy types that must resolve to a mapped target project (via project_mapping).
_OWNED_TYPES = frozenset({"task", "attempt", "approval", "evidence", "file"})


def source_key(source_store_id: str, legacy_type: str, legacy_id: str) -> str:
    return f"{source_store_id}\x1f{legacy_type}\x1f{legacy_id}"


def derive_object_id(source_store_id: str, legacy_type: str, legacy_id: str) -> str:
    """Deterministic, idempotent object identity for an imported fact."""
    digest = sha256_digest(
        {"source_store_id": source_store_id, "legacy_type": legacy_type,
         "legacy_id": legacy_id}
    )
    return "legacy-" + digest[:40]


@dataclass(frozen=True)
class ImportedFact:
    source_store_id: str
    legacy_type: str
    legacy_id: str
    source_digest: str
    classification: str
    object_id: str
    target_project_id: str
    raw: dict[str, Any]
    parent_refs: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return source_key(self.source_store_id, self.legacy_type, self.legacy_id)

    @property
    def is_ok(self) -> bool:
        return self.classification == Classification.OK

    def payload(self, batch_id: str) -> dict[str, Any]:
        """Typed payload persisted into the revision ledger (raw retained)."""
        return {
            "source_store_id": self.source_store_id,
            "legacy_type": self.legacy_type,
            "legacy_id": self.legacy_id,
            "source_digest": self.source_digest,
            "batch_id": batch_id,
            "classification": self.classification,
            "raw": self.raw,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.key,
            "legacy_type": self.legacy_type,
            "legacy_id": self.legacy_id,
            "source_digest": self.source_digest,
            "classification": self.classification,
            "object_id": self.object_id,
            "target_project_id": self.target_project_id,
            "parent_refs": list(self.parent_refs),
        }


class LegacyMapper:
    """Maps legacy records to idempotent ImportedFact candidates.

    ``project_mapping`` is an explicit ``{legacy_project_id: target_project_id}``
    supplied by the caller. Same-name projects are never merged: a legacy
    project absent from the mapping is classified ``unowned``.
    """

    def __init__(self, source_store_id: str, target_project_id: str,
                 project_mapping: dict[str, str]):
        self.source_store_id = source_store_id
        self.target_project_id = target_project_id
        self.project_mapping = dict(project_mapping)

    def map_all(self, records: tuple[LegacyRecord, ...]) -> tuple[ImportedFact, ...]:
        by_id: dict[tuple[str, str], LegacyRecord] = {}
        # First pass: detect in-source duplicates (same legacy_id, different content).
        seen: dict[tuple[str, str], str] = {}
        duplicates: set[tuple[str, str]] = set()
        for rec in records:
            key = (rec.legacy_type, rec.legacy_id)
            prev = seen.get(key)
            if prev is not None and prev != rec.source_digest:
                duplicates.add(key)
            else:
                seen[key] = rec.source_digest
            by_id[key] = rec

        facts: list[ImportedFact] = []
        for rec in records:
            classification = self._classify(rec, by_id, duplicates)
            facts.append(ImportedFact(
                source_store_id=self.source_store_id,
                legacy_type=rec.legacy_type,
                legacy_id=rec.legacy_id,
                source_digest=rec.source_digest,
                classification=classification,
                object_id=derive_object_id(self.source_store_id, rec.legacy_type,
                                           rec.legacy_id),
                target_project_id=self.target_project_id,
                raw=rec.raw,
                parent_refs=rec.parent_refs,
            ))
        return tuple(facts)

    def _classify(self, rec: LegacyRecord,
                  by_id: dict[tuple[str, str], LegacyRecord],
                  duplicates: set[tuple[str, str]]) -> str:
        key = (rec.legacy_type, rec.legacy_id)
        if key in duplicates:
            return Classification.DUPLICATE

        if rec.legacy_type in _OWNED_TYPES:
            if rec.owner_project_ref is None or rec.owner_project_ref not in self.project_mapping:
                return Classification.UNOWNED

        for parent_ref in rec.parent_refs:
            parent = _find_parent(parent_ref, by_id)
            if parent is None:
                return Classification.ORPHAN
            parent_key = (parent.legacy_type, parent.legacy_id)
            if parent_key in duplicates:
                return Classification.MISSING_HISTORY
            if parent.legacy_type in _OWNED_TYPES and (
                    parent.owner_project_ref is None
                    or parent.owner_project_ref not in self.project_mapping):
                return Classification.MISSING_HISTORY

        return Classification.OK


def _find_parent(parent_ref: str,
                 by_id: dict[tuple[str, str], LegacyRecord]) -> LegacyRecord | None:
    for (_legacy_type, legacy_id), rec in by_id.items():
        if legacy_id == parent_ref:
            return rec
    return None
