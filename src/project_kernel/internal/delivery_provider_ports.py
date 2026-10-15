"""Injected provider port for delivery effects and effect observation.

The application owns authorization, immutable manifests, and ledger state. A
provider owns the external sink and the read operation that can establish its
effect. Providers must return ``unknown`` evidence when they cannot establish
what happened; the application never retries an unobserved write.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class DeliveryProvider(Protocol):
    """Perform and observe delivery effects for explicitly configured targets.

    ``sink_ids`` lists the allowed sink names. ``target_matches`` checks every
    provider-specific target field that identifies the approved destination.
    """

    sink_ids: frozenset[str]

    def target_matches(self, target: Mapping[str, Any], *, scope_mode: str) -> bool:
        """Return whether an approved target names this provider's sink."""

    def apply(self, manifest: Any, sink_id: str, operation_id: str) -> Mapping[str, Any]:
        """Publish the frozen manifest once and return serializable receipt fields.

        ``operation_id`` is the durable effect identity. An exception leaves
        the outcome unknown until a read can establish the external effect.
        """

    def observe(self, operation_id: str, manifest_id: str,
                expected_digest: str | None, *, provider_state: str | None = None,
                manifest: Any | None = None) -> Any:
        """Read effect evidence without writing, repairing, or retrying delivery.

        ``applied`` requires the matching operation and verified manifest digest;
        ``absent_final`` requires terminal execution or stored fence evidence.
        Exceptions and invalid observations cannot release a delivery blocker.
        """
