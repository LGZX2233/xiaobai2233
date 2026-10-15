"""Read-only legacy migration and reconciliation (P07).

The legacy source is never modified: we only read bytes, compute hashes, and
optionally open the legacy SQLite in read-only mode. Importing maps legacy
records into the generic revision ledger idempotently and quarantines anything
that cannot be reconciled; nothing is silently dropped or defaulted to success.
"""
from __future__ import annotations

from .manifest import (
    FileEntry,
    LegacySourceManifest,
    TableCount,
    build_source_manifest,
)
from .source import LegacyReader, LegacyRecord, LegacySnapshot, SyntheticLegacySample
from .mapper import (
    Classification,
    ImportedFact,
    LegacyMapper,
    derive_object_id,
    source_key,
)
from .quarantine import Quarantine, QuarantineItem, RepairAction, RepairPlan, repair_plan
from .reconcile import ReconcileEntry, ReconcileReport, reconcile
from .importer import ImportPlan, ImportReport, LegacyImportService

__all__ = [
    "FileEntry",
    "LegacySourceManifest",
    "TableCount",
    "build_source_manifest",
    "LegacyReader",
    "LegacyRecord",
    "LegacySnapshot",
    "SyntheticLegacySample",
    "Classification",
    "ImportedFact",
    "LegacyMapper",
    "derive_object_id",
    "source_key",
    "Quarantine",
    "QuarantineItem",
    "RepairAction",
    "RepairPlan",
    "repair_plan",
    "ReconcileEntry",
    "ReconcileReport",
    "reconcile",
    "ImportPlan",
    "ImportReport",
    "LegacyImportService",
]
