"""Effect-only ports consumed after application authorization and commit.

Provider configuration and restore target descriptions are captured before a
command starts. Reconciliation observes completed effects without repeating them.
These interfaces are internal and do not extend the frozen v1 service ports.
"""
from typing import Any, Protocol


class EnvironmentProbe(Protocol):
    """Inspect pinned recipe requirements without changing the environment."""

    def probe(self, recipes: list[dict[str, Any]]) -> dict[str, Any]: ...


class EvidenceEffects(Protocol):
    """Configured evidence effects; authorization and ledger writes stay in the application."""

    artifact_available: bool
    sink_ids: frozenset[str]
    backup_available: bool
    restore_target_info: dict[str, Any] | None

    def register_artifact(self, staged: dict, payload: dict) -> dict: ...
    def archive(self, manifest: Any, sink_id: str, operation_id: str, *,
                repair: bool, original_effect_id: str | None = None) -> dict: ...
    def backup(self, operation_id: str) -> dict: ...
    def restore(self, source: dict, operation_id: str) -> dict: ...
    def reconcile_archive(self, manifest: Any, sink_id: str) -> dict | None: ...
    def reconcile_restore(self, source: dict, operation_id: str) -> dict | None: ...
    def reconcile_backup(self, operation_id: str) -> dict | None: ...
