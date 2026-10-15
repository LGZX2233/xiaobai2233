"""Idempotent legacy import service.

Ties the read-only manifest + mapper + quarantine + reconciliation together and
persists ``ok`` facts into the generic revision ledger exactly once. Re-running
the same batch against the same target store adds no new revision, audit event
or commit: facts whose identity already exists with a matching source digest
are skipped, and conflicting content is quarantined as ``duplicate``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...contracts.digest import sha256_digest
from ...contracts.dto import CommandContext, ObjectRef, ResolvedScope
from ...data.store.store import Store
from ...data.store.uow import UnitOfWork
from .manifest import LegacySourceManifest, build_source_manifest
from .mapper import Classification, ImportedFact, LegacyMapper
from .quarantine import Quarantine
from .reconcile import reconcile
from .source import LegacyReader, LegacyRecord

IMPORTED_FACT_TYPE = "imported_fact"
POINTER = "current"


@dataclass(frozen=True)
class ImportPlan:
    source_store_id: str
    target_project_id: str
    batch_id: str
    manifest: LegacySourceManifest
    records: tuple[LegacyRecord, ...]
    facts: tuple[ImportedFact, ...]


@dataclass(frozen=True)
class MappingEntry:
    source_key: str
    legacy_type: str
    legacy_id: str
    source_digest: str
    classification: str
    object_id: str
    new_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"source_key": self.source_key, "legacy_type": self.legacy_type,
                "legacy_id": self.legacy_id, "source_digest": self.source_digest,
                "classification": self.classification, "object_id": self.object_id,
                "new_ref": self.new_ref}


@dataclass(frozen=True)
class ImportReport:
    plan: ImportPlan
    imported: int
    skipped_existing: int
    quarantined: int
    by_classification: dict[str, int]
    mapping: tuple[MappingEntry, ...]
    manifest_digest: str
    quarantine_path: str | None = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_store_id": self.plan.source_store_id,
            "target_project_id": self.plan.target_project_id,
            "batch_id": self.plan.batch_id,
            "manifest_digest": self.manifest_digest,
            "imported": self.imported,
            "skipped_existing": self.skipped_existing,
            "quarantined": self.quarantined,
            "by_classification": self.by_classification,
            "mapping": [m.to_dict() for m in self.mapping],
            "quarantine_path": self.quarantine_path,
            "dry_run": self.dry_run,
        }


def _new_batch_id() -> str:
    return "legacy-" + uuid.uuid4().hex


def plan_import(source_store_id: str, target_project_id: str, batch_id: str,
                manifest: LegacySourceManifest, records: tuple[LegacyRecord, ...],
                project_mapping: dict[str, str]) -> ImportPlan:
    """Purely map an immutable source snapshot into import candidates."""
    facts = LegacyMapper(source_store_id, target_project_id, project_mapping).map_all(records)
    return ImportPlan(source_store_id, target_project_id, batch_id, manifest, records, facts)


class LegacyImportService:
    """Read-only legacy import into an explicitly chosen target project."""

    def __init__(self, store: Store, source_root: Path, quarantine_root: Path,
                 source_store_id: str, target_project_id: str,
                 project_mapping: dict[str, str], batch_id: str | None = None,
                 principal_id: str = "reconciler"):
        self.store = store
        self.source_root = Path(source_root)
        self.quarantine = Quarantine(quarantine_root)
        self.source_store_id = source_store_id
        self.target_project_id = target_project_id
        self.project_mapping = dict(project_mapping)
        self.batch_id = batch_id or _new_batch_id()
        self.principal_id = principal_id

    # -- planning ---------------------------------------------------------
    def read_plan(self) -> ImportPlan:
        manifest = build_source_manifest(self.source_root, self.source_store_id)
        records = LegacyReader(self.source_root, self.source_store_id).read()
        mapper = LegacyMapper(self.source_store_id, self.target_project_id,
                              self.project_mapping)
        facts = mapper.map_all(records)
        return ImportPlan(source_store_id=self.source_store_id,
                          target_project_id=self.target_project_id,
                          batch_id=self.batch_id, manifest=manifest,
                          records=records, facts=facts)

    # -- idempotent persistence ------------------------------------------
    def import_batch(self, dry_run: bool = False) -> ImportReport:
        plan = self.read_plan()

        to_write: list[ImportedFact] = []
        skipped = 0
        facts_after_check: list[ImportedFact] = []
        for fact in plan.facts:
            if not fact.is_ok:
                facts_after_check.append(fact)
                continue
            existing = self._read_existing(fact.object_id)
            if existing is None:
                to_write.append(fact)
                facts_after_check.append(fact)
            elif existing.get("source_digest") == fact.source_digest:
                skipped += 1
                facts_after_check.append(fact)
            else:
                facts_after_check.append(self._as_duplicate(fact))

        if dry_run:
            return self._build_report(plan, facts_after_check, 0, skipped,
                                      dry_run=True)

        if to_write:
            self._persist(to_write)

        quarantine_path = None
        if any(not f.is_ok for f in facts_after_check):
            quarantine_path = str(self.quarantine.write(self.batch_id,
                                                        tuple(facts_after_check)))
        return self._build_report(plan, facts_after_check, len(to_write), skipped,
                                  dry_run=False, quarantine_path=quarantine_path)

    def _read_existing(self, object_id: str) -> dict[str, Any] | None:
        row = self.store.conn.execute(
            "SELECT 1 FROM entity WHERE project_id=? AND type=? AND object_id=?",
            (self.target_project_id, IMPORTED_FACT_TYPE, object_id),
        ).fetchone()
        if row is None:
            return None
        rev = self.store.get_revision(
            ObjectRef(self.target_project_id, IMPORTED_FACT_TYPE, object_id, "rev-1"))
        if rev is None:
            return None
        payload = rev.get("payload") or {}
        return {"source_digest": payload.get("source_digest"), "payload": payload}

    @staticmethod
    def _as_duplicate(fact: ImportedFact) -> ImportedFact:
        return ImportedFact(
            source_store_id=fact.source_store_id, legacy_type=fact.legacy_type,
            legacy_id=fact.legacy_id, source_digest=fact.source_digest,
            classification=Classification.DUPLICATE, object_id=fact.object_id,
            target_project_id=fact.target_project_id, raw=fact.raw,
            parent_refs=fact.parent_refs)

    def _persist(self, to_write: list[ImportedFact]) -> None:
        scope = ResolvedScope(
            project_id=self.target_project_id, store_id=self.store.store_id,
            principal_id=self.principal_id,
            capabilities=frozenset({"project.read", "project.admin"}),
            mode="test",
        )
        input_hash = sha256_digest({
            "batch_id": self.batch_id,
            "source_store_id": self.source_store_id,
            "target_project_id": self.target_project_id,
            "project_mapping": self.project_mapping,
            "source_keys": sorted(f.key for f in to_write),
        })
        context = CommandContext(
            scope=scope,
            command_id="cmd-legacy-import",
            idempotency_key=self.batch_id,
            input_hash=input_hash,
        )
        uow = UnitOfWork(self.store, context, "legacy.import")

        def write(handles: Any) -> None:
            refs: list[ObjectRef] = []
            for fact in to_write:
                ref = handles.records.append_revision(
                    IMPORTED_FACT_TYPE, fact.object_id, fact.payload(self.batch_id),
                    "legacy/imported-fact")
                handles.records.publish_head(ref, POINTER, expected_head_version=None)
                refs.append(ref)
            handles.audit(
                "legacy.import",
                payload={"batch_id": self.batch_id, "imported": len(refs),
                         "source_store_id": self.source_store_id},
                event_schema="v1",
                object_refs=[r.to_dict() for r in refs],
                source_key={"source_store_id": self.source_store_id,
                            "batch_id": self.batch_id},
            )

        uow.execute(write)

    def _build_report(self, plan: ImportPlan, facts: tuple[ImportedFact, ...],
                      imported: int, skipped: int, *, dry_run: bool,
                      quarantine_path: str | None = None) -> ImportReport:
        by_classification: dict[str, int] = {c: 0 for c in
                                             (Classification.OK, Classification.ORPHAN,
                                              Classification.UNOWNED,
                                              Classification.DUPLICATE,
                                              Classification.MISSING_HISTORY)}
        mapping: list[MappingEntry] = []
        quarantined = 0
        for fact in facts:
            by_classification[fact.classification] = by_classification.get(fact.classification, 0) + 1
            if not fact.is_ok:
                quarantined += 1
            new_ref = (f"{self.target_project_id}:{IMPORTED_FACT_TYPE}:{fact.object_id}:rev-1"
                       if fact.is_ok else None)
            mapping.append(MappingEntry(
                source_key=fact.key, legacy_type=fact.legacy_type,
                legacy_id=fact.legacy_id, source_digest=fact.source_digest,
                classification=fact.classification, object_id=fact.object_id,
                new_ref=new_ref))
        return ImportReport(
            plan=plan, imported=imported, skipped_existing=skipped,
            quarantined=quarantined, by_classification=by_classification,
            mapping=tuple(mapping), manifest_digest=plan.manifest.digest,
            quarantine_path=quarantine_path, dry_run=dry_run)

    # -- reconciliation ---------------------------------------------------
    def reconcile(self, plan: ImportPlan) -> Any:
        persisted: dict[tuple[str, str], dict[str, Any]] = {}
        for fact in plan.facts:
            if not fact.is_ok:
                continue
            existing = self._read_existing(fact.object_id)
            if existing is not None:
                persisted[(fact.legacy_type, fact.legacy_id)] = existing["payload"]
        return reconcile(self.source_store_id, self.target_project_id,
                         plan.records, plan.facts, persisted)
