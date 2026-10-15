"""Quarantine and repair plan for legacy records that cannot be imported.

Nothing is silently skipped: every non-ok record is written to an explicit
quarantine directory with its raw payload, and a repair plan maps each issue to
a concrete recovery action.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mapper import Classification, ImportedFact


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class QuarantineItem:
    source_key: str
    legacy_type: str
    legacy_id: str
    source_digest: str
    reason: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "legacy_type": self.legacy_type,
            "legacy_id": self.legacy_id,
            "source_digest": self.source_digest,
            "reason": self.reason,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class RepairAction:
    source_key: str
    issue: str
    recovery_action: str

    def to_dict(self) -> dict[str, Any]:
        return {"source_key": self.source_key, "issue": self.issue,
                "recovery_action": self.recovery_action}


@dataclass(frozen=True)
class RepairPlan:
    actions: tuple[RepairAction, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"actions": [a.to_dict() for a in self.actions]}


_RECOVERY: dict[str, str] = {
    Classification.UNOWNED:
        "add an explicit project_mapping entry for the record's legacy project id, then re-run",
    Classification.ORPHAN:
        "import the referenced parent record(s) first (or mark their owner project unmapped)",
    Classification.DUPLICATE:
        "resolve the conflicting source records to one canonical source_digest, then re-run",
    Classification.MISSING_HISTORY:
        "repair the parent lineage: import the parent(s) and resolve their classification first",
}


def repair_plan(items: tuple[QuarantineItem, ...]) -> RepairPlan:
    return RepairPlan(tuple(
        RepairAction(source_key=it.source_key, issue=it.reason,
                     recovery_action=_RECOVERY.get(it.reason, "manual review"))
        for it in items
    ))


class Quarantine:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write(self, batch_id: str, facts: tuple[ImportedFact, ...]) -> Path:
        """Persist quarantined records (raw included) under root/<batch_id>/."""
        items = tuple(
            QuarantineItem(source_key=f.key, legacy_type=f.legacy_type, legacy_id=f.legacy_id,
                           source_digest=f.source_digest, reason=f.classification, raw=f.raw)
            for f in facts if not f.is_ok
        )
        batch_dir = self.root / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "batch_id": batch_id,
            "created_at": _utc_now(),
            "count": len(items),
            "items": [it.to_dict() for it in items],
            "repair_plan": repair_plan(items).to_dict(),
        }
        (batch_dir / "quarantine-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw_dir = batch_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        for it in items:
            safe = it.source_key.replace("\x1f", "__").replace("\\", "_").replace("/", "_")
            (raw_dir / f"{safe}.json").write_text(
                json.dumps(it.raw, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return batch_dir
