"""Shared authorization for project application services."""
from __future__ import annotations

from ..contracts.dto import ResolvedScope
from ..contracts.errors import KernelError, permission_denied, scope_mismatch


def require_scope(store, scope: ResolvedScope, capability: str | None = None) -> None:
    """Require the resolved project/store and the exact granted capability."""
    if scope.project_id != store.project_id or scope.store_id != store.store_id:
        raise KernelError(scope_mismatch("resolved scope does not match the project store"))
    if capability is not None and not scope.has(capability):
        raise KernelError(permission_denied(f"capability {capability!r} is required"))
