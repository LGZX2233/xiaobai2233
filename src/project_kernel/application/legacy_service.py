"""Authorized test-only legacy import over an injected immutable snapshot provider."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any, Iterable, Mapping

from ..contracts import sha256_digest
from ..contracts.dto import CommandContext, ObjectRef
from ..contracts.errors import (KernelError, idempotency_conflict, invalid_input,
                                permission_denied, reference_not_found)
from ..data.store.uow import UnitOfWork
from ..migration.legacy.importer import IMPORTED_FACT_TYPE, POINTER, ImportReport, MappingEntry, plan_import
from ..migration.legacy.mapper import Classification
from ..migration.legacy.manifest import LegacySourceManifest
from ..migration.legacy.source import LegacyRecord, LegacySnapshot
from .security import require_scope
from .design.references import checked_payload


def snapshot_digest(source_store_id: str, manifest: LegacySourceManifest,
                    records: Iterable[LegacyRecord]) -> str:
    return sha256_digest({"source_store_id": source_store_id,
                          "manifest_digest": manifest.digest,
                          "records": [record.to_dict() for record in records]})


def _value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


class LegacyImportEntry:
    """Imports only a configured synthetic snapshot; payloads contain references, never paths."""

    def __init__(self, store, *, snapshot_provider: Any,
                 trusted_snapshot_producers: Mapping[str, Iterable[str]]):
        self.store = store
        self.snapshot_provider = snapshot_provider
        self.trusted_snapshot_producers = {
            principal: frozenset(source_ids)
            for principal, source_ids in trusted_snapshot_producers.items()
        }

    def import_legacy(self, ctx: CommandContext, payload: Mapping[str, Any]):
        require_scope(self.store, ctx.scope, "project.admin")
        if ctx.scope.mode != "test":
            raise KernelError(permission_denied("legacy import is available only in test mode"))
        payload = checked_payload("legacy.import", payload)
        try:
            snapshot_ref = ObjectRef.from_dict(payload["source_snapshot_ref"])
            plan_ref = ObjectRef.from_dict(payload["import_plan_ref"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KernelError(invalid_input("legacy import requires exact snapshot and plan references")) from exc
        if snapshot_ref.project_id != self.store.project_id or plan_ref.project_id != self.store.project_id:
            raise KernelError(invalid_input("legacy import references must belong to the target project"))
        if snapshot_ref.object_type != "legacy_source_snapshot" or plan_ref.object_type != "legacy_import_plan":
            raise KernelError(invalid_input("legacy import reference types are invalid"))
        snapshot_row = self.store.get_revision(snapshot_ref)
        plan_row = self.store.get_revision(plan_ref)
        if snapshot_row is None or plan_row is None:
            raise KernelError(reference_not_found("legacy snapshot or import plan revision not found"))
        if not isinstance(snapshot_row["payload"], dict) or not isinstance(plan_row["payload"], dict):
            raise KernelError(invalid_input("snapshot and plan revisions must contain objects"))

        producer = snapshot_row["principal_id"]
        plan = plan_row["payload"]
        source_store_id = snapshot_row["payload"].get("source_store_id")
        if source_store_id not in self.trusted_snapshot_producers.get(producer, ()):
            raise KernelError(permission_denied("snapshot producer is not trusted for this source store"))
        if (plan.get("target_project_id") != self.store.project_id
                or plan.get("target_store_id") != self.store.store_id
                or plan.get("source_store_id") != source_store_id
                or plan.get("source_snapshot_ref") != snapshot_ref.to_dict()):
            raise KernelError(invalid_input("import plan target or source binding differs"))
        if plan_row["principal_id"] != ctx.scope.principal_id:
            raise KernelError(permission_denied("import plan was not authored by this principal"))
        existing_receipt = self.store.get_receipt(ctx.scope.principal_id, ctx.idempotency_key)
        if existing_receipt is not None:
            if existing_receipt["input_hash"] != ctx.input_hash:
                raise KernelError(idempotency_conflict(
                    "legacy import idempotency key was reused with different snapshot or plan"))
            from ..data.store.uow import _receipt_from_dict
            return _receipt_from_dict(existing_receipt["receipt"])
        mapping = plan.get("project_mapping")
        if (not isinstance(mapping, dict)
                or any(not isinstance(key, str) or not key for key in mapping)
                or any(value != self.store.project_id for value in mapping.values())):
            raise KernelError(invalid_input("project mapping must map only into this target project"))

        supplied = self.snapshot_provider.read_snapshot(snapshot_ref)
        if not isinstance(supplied, LegacySnapshot):
            raise KernelError(invalid_input("snapshot provider must return a LegacySnapshot"))
        snap = {name: getattr(supplied, name) for name in
                ("ref", "digest", "source_store_id", "records", "manifest", "producer_principal_id")}
        supplied_ref = ObjectRef.from_dict(_value(snap["ref"]))
        if supplied_ref != snapshot_ref or snap["source_store_id"] != source_store_id:
            raise KernelError(invalid_input("snapshot provider returned a different source snapshot"))
        if snap.get("producer_principal_id") != producer:
            raise KernelError(permission_denied("snapshot provider producer differs from the persisted revision author"))
        manifest_raw = snap["manifest"]
        if isinstance(manifest_raw, LegacySourceManifest):
            manifest = manifest_raw
        else:
            raise KernelError(invalid_input("snapshot provider must return an immutable LegacySourceManifest"))
        supplied_records = tuple(snap["records"])
        if not all(isinstance(record, LegacyRecord) for record in supplied_records):
            raise KernelError(invalid_input("snapshot records must be immutable LegacyRecord values"))
        records = tuple(LegacyRecord(
            legacy_type=item["legacy_type"], legacy_id=item["legacy_id"],
            source_digest=item["source_digest"], raw=item["raw"],
            owner_project_ref=item.get("owner_project_ref"),
            parent_refs=tuple(item.get("parent_refs", ())),
            attempt_status=item.get("attempt_status"), selected=item.get("selected"),
            approval_decision=item.get("approval_decision"),
            evidence_refs=tuple(item.get("evidence_refs", ())),
            file_refs=tuple(item.get("file_refs", ())))
            for item in (json.loads(json.dumps(record.to_dict(), ensure_ascii=False))
                         for record in supplied_records))
        if any(record.source_digest != sha256_digest(record.raw) for record in records):
            raise KernelError(invalid_input("legacy record digest differs from its raw payload"))
        if manifest.source_store_id != source_store_id:
            raise KernelError(invalid_input("snapshot manifest source store differs"))
        immutable_snapshot = LegacySnapshot(snapshot_ref, "", source_store_id, records,
                                            manifest, producer)
        actual_digest = sha256_digest(immutable_snapshot.digest_body())
        if actual_digest != snap["digest"] or actual_digest != snapshot_row["payload"].get("snapshot_digest"):
            raise KernelError(invalid_input("source snapshot digest does not match its pinned revision"))
        if plan.get("manifest_digest") != manifest.digest:
            raise KernelError(invalid_input("import plan manifest digest differs from snapshot"))
        batch_id = plan.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            raise KernelError(invalid_input("import plan batch_id is required"))

        import_plan = plan_import(source_store_id, self.store.project_id, batch_id,
                                  manifest, records, mapping)
        def cb(h):
            imported = skipped = 0
            refs = []
            mapping_entries = []
            persisted_refs = {}
            counts = {c: 0 for c in (Classification.OK, Classification.ORPHAN,
                                      Classification.UNOWNED, Classification.DUPLICATE,
                                      Classification.MISSING_HISTORY)}
            for fact in import_plan.facts:
                classification = fact.classification
                existing_ref = None
                current = self.store.get_head(IMPORTED_FACT_TYPE, fact.object_id, POINTER)
                current_payload = None
                if current is not None:
                    existing_ref = ObjectRef(self.store.project_id, IMPORTED_FACT_TYPE,
                                             fact.object_id, current["revision_id"])
                    row = self.store.get_revision(existing_ref)
                    current_payload = row["payload"] if row else None
                if current_payload is not None:
                    if current_payload.get("source_digest") == fact.source_digest:
                        skipped += 1
                    else:
                        classification = Classification.DUPLICATE
                if classification == Classification.OK and current_payload is None:
                    ref = h.records.append_revision(IMPORTED_FACT_TYPE, fact.object_id,
                        fact.payload(batch_id), "legacy/imported-fact")
                    h.records.publish_head(ref, POINTER, expected_head_version=None)
                    refs.append(ref)
                    imported += 1
                    new_ref = ref.to_dict()
                    persisted_refs[fact.object_id] = new_ref
                else:
                    new_ref = (existing_ref.to_dict() if current_payload is not None
                               and classification == Classification.OK else None)
                    if new_ref is not None:
                        persisted_refs[fact.object_id] = new_ref
                counts[classification] = counts.get(classification, 0) + 1
                if classification != Classification.OK:
                    quarantine_body = {**fact.payload(batch_id), "classification": classification,
                                       "quarantined": True}
                    qid = "quarantine-" + sha256_digest({"source_key": fact.key,
                        "source_digest": fact.source_digest})[:40]
                    qhead = self.store.get_head("legacy_quarantine", qid, POINTER)
                    if qhead is None:
                        qref = h.records.append_revision("legacy_quarantine", qid,
                            quarantine_body, "legacy/quarantine-fact")
                        h.records.publish_head(qref, POINTER, expected_head_version=None)
                        refs.append(qref)
                mapping_entries.append(MappingEntry(fact.key, fact.legacy_type, fact.legacy_id,
                    fact.source_digest, classification, fact.object_id,
                    (f"{new_ref['project_id']}:{new_ref['object_type']}:{new_ref['object_id']}:{new_ref['revision_id']}"
                     if new_ref is not None else None)))
            quarantined = sum(1 for entry in mapping_entries if entry.classification != Classification.OK)
            report = ImportReport(import_plan, imported, skipped, quarantined, counts,
                                  tuple(mapping_entries), manifest.digest, None, False).to_dict()
            report_id = "legacy-import-report-" + sha256_digest({
                "source_snapshot_ref": snapshot_ref.to_dict(), "import_plan_ref": plan_ref.to_dict()})[:32]
            report_head = self.store.get_head("legacy_import_report", report_id, POINTER)
            if report_head is not None:
                h.outcome.object_refs = tuple(refs) + (ObjectRef(self.store.project_id,
                    "legacy_import_report", report_id, report_head["revision_id"]),)
                h.outcome.operation_id = report_id
                return
            rref = h.records.append_revision("legacy_import_report", report_id,
                {**report, "source_snapshot_ref": snapshot_ref.to_dict(),
                 "import_plan_ref": plan_ref.to_dict(), "status": "completed"},
                "legacy/import-report")
            h.records.publish_head(rref, POINTER,
                expected_head_version=str(report_head["head_version"]) if report_head else None)
            refs.append(rref)
            h.audit("legacy.imported", {"batch_id": batch_id, "imported": imported,
                     "skipped_existing": skipped, "quarantined": quarantined,
                     "manifest_digest": manifest.digest}, object_refs=[r.to_dict() for r in refs])
            h.outcome.object_refs = tuple(refs)
            h.outcome.operation_id = report_id
        return UnitOfWork(self.store, ctx, "legacy.import").execute(cb)
