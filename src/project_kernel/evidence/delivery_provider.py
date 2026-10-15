"""Filesystem implementation of the injected delivery provider.

This module is the only delivery layer that knows how a bundle sink locates,
writes, and verifies exported files. ``DeliveryService`` receives only this
provider's receipts and effect observations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from ..contracts import EffectStatus
from ..contracts.dto import EffectReceipt
from ..domain import delivery as delivery_rules
from .archive import ArchiveManifest, BundleExporter


class BundleDeliveryProvider:
    """Adapt a configured :class:`BundleExporter` to ``DeliveryProvider``."""

    def __init__(self, exporter: BundleExporter,
                 *, effect_query: Callable[[str], Any] | None = None) -> None:
        self.exporter = exporter
        self.effect_query = effect_query
        self.sink_ids = (frozenset({"exports"}) if exporter.allowed_sinks is None
                         else exporter.allowed_sinks)

    def target_matches(self, target: Mapping[str, Any], *, scope_mode: str) -> bool:
        """Check sink identity and, when present, the approved output root."""
        if target.get("sink_id") not in self.sink_ids:
            return False
        approved_root = target.get("exports_root")
        if approved_root is None:
            return scope_mode == "test"
        if not isinstance(approved_root, str) or not approved_root:
            return False
        return Path(approved_root).resolve() == self.exporter.exports_root.resolve()

    def apply(self, manifest: ArchiveManifest, sink_id: str,
              operation_id: str) -> Mapping[str, Any]:
        """Export the frozen manifest and return a serializable sink receipt."""
        receipt = self.exporter.export(manifest, sink_id, lease_token=operation_id)
        return receipt.to_dict()

    def observe(self, operation_id: str, manifest_id: str,
                expected_digest: str | None, *, provider_state: str | None = None,
                manifest: ArchiveManifest | None = None) -> EffectReceipt:
        """Observe the sink without writing or repairing it."""
        if self.effect_query is not None:
            return self.effect_query(operation_id)
        target = self.exporter._target(manifest_id)
        present = target.exists()
        digest_matches: bool | None = None
        if present and manifest is not None:
            try:
                digest_matches = (manifest.digest() == expected_digest
                                  and not self.exporter._verify_export(target, manifest))
            except (OSError, ValueError):
                digest_matches = None
        terminal = provider_state == "failed"
        status = delivery_rules.classify_effect(target_present=present,
                                                digest_matches=digest_matches,
                                                execution_terminal=terminal)
        return EffectReceipt(
            operation_id, status, execution_terminal=terminal,
            verified_digest=(expected_digest
                             if status == EffectStatus.APPLIED.value else None))
