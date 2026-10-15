"""Trusted invocation-context handles (design 04 §2).

``invocation_context_id`` is a short-lived handle minted by the trusted CLI/Host
entry after resolving the real principal. The service only *looks the handle up*
— it never trusts a caller-supplied actor string, and the handle must never
reach the model payload, the idempotency hash, logs, snapshots or durable
business payloads.

Handles carry a deadline so a leaked/old handle cannot be replayed forever;
both an unminted and an expired handle are refused with PERMISSION_DENIED
(04 §6 has no separate expiry code — the caller must re-establish a trusted
context, it may not retry with a different actor).
"""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from ...contracts.errors import (
    BlockError,
    KernelError,
    human_identity_unavailable,
    permission_denied,
)

#: The trusted context of the request being handled. Handlers read the principal
#: and capabilities from here instead of from the wire params, so the handle
#: itself never has to be forwarded into business code.
CURRENT_MACHINE_CONTEXT: ContextVar["MachineContext | None"] = ContextVar(
    "kernel_machine_context", default=None)

#: The envelope field carrying the handle; excluded from hashes and logs.
INVOCATION_CONTEXT_FIELD = "invocation_context_id"

#: jsonrpc id / invocation handle pattern (see command-envelope.schema.json).
HANDLE_PATTERN_MAX = 128

DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MAX_HANDLES = 1024


@dataclass(frozen=True)
class MachineContext:
    """What a resolved handle actually certifies."""

    handle_id: str
    principal_id: str
    capabilities: frozenset[str] = frozenset()
    project_id: str | None = None
    connection_id: str | None = None
    human_verified: bool = False

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True)
class InteractionProof:
    """Evidence that a *real user* interaction produced this handle.

    A future Host must be able to point at a verifiable interaction source;
    without one no human handle may be minted (04 §2).
    """

    source: str
    verified: bool
    detail: str = ""


@dataclass(frozen=True)
class _Entry:
    context: MachineContext
    expires_at: float


class InvocationContextRegistry:
    """Mints and resolves short-lived handles with a bounded TTL.

    The clock is injectable so expiry is testable without sleeping.
    """

    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic,
                 max_handles: int = DEFAULT_MAX_HANDLES,
                 handle_factory: Callable[[], str] | None = None) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_handles < 1:
            raise ValueError("max_handles must be >= 1")
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._max_handles = max_handles
        self._factory = handle_factory or (lambda: "ctx-" + uuid.uuid4().hex[:16])
        self._entries: dict[str, _Entry] = {}

    # -- minting ----------------------------------------------------------
    def mint(self, principal_id: str, capabilities: Iterable[str] = (),
             *, project_id: str | None = None, connection_id: str | None = None,
             ttl_seconds: float | None = None, human_verified: bool = False) -> str:
        if not principal_id:
            raise ValueError("principal_id is required to mint a context")
        ttl = self.ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        context = MachineContext(
            handle_id="",
            principal_id=principal_id,
            capabilities=frozenset(capabilities),
            project_id=project_id,
            connection_id=connection_id,
            human_verified=human_verified,
        )
        self._evict_if_needed()
        for _ in range(8):
            handle = self._factory()
            _require_handle_syntax(handle)
            if handle not in self._entries:
                break
        else:  # pragma: no cover - collision storm
            raise RuntimeError("could not allocate a unique invocation handle")
        self._entries[handle] = _Entry(
            context=MachineContext(
                handle_id=handle,
                principal_id=context.principal_id,
                capabilities=context.capabilities,
                project_id=context.project_id,
                connection_id=context.connection_id,
                human_verified=context.human_verified,
            ),
            expires_at=self._clock() + ttl,
        )
        return handle

    def mint_human(self, principal_id: str, capabilities: Iterable[str] = (),
                   *, proof: InteractionProof | None, project_id: str | None = None,
                   connection_id: str | None = None,
                   ttl_seconds: float | None = None) -> str:
        """Mint a human handle only with verified interaction evidence."""
        if proof is None or not proof.verified:
            raise KernelError(human_identity_unavailable())
        return self.mint(principal_id, capabilities, project_id=project_id,
                         connection_id=connection_id, ttl_seconds=ttl_seconds,
                         human_verified=True)

    # -- resolving --------------------------------------------------------
    def resolve(self, handle: str, *, now: float | None = None) -> MachineContext | None:
        """Return the bound context, or ``None`` if unminted/expired/unknown.

        An expired entry is kept (not dropped) so a repeated attempt is still
        reported as *expired* rather than *never minted*; it is reclaimed by
        :meth:`purge_expired` and by the capacity bound on mint.
        """
        if not isinstance(handle, str) or not handle:
            return None
        entry = self._entries.get(handle)
        if entry is None:
            return None
        instant = self._clock() if now is None else now
        if entry.expires_at <= instant:
            return None
        return entry.context

    def resolve_required(self, handle: str, *, now: float | None = None) -> MachineContext:
        """Like :meth:`resolve` but raises the frozen PERMISSION_DENIED error."""
        if not isinstance(handle, str) or not handle or handle not in self._entries:
            raise KernelError(_unminted_error())
        entry = self._entries[handle]
        instant = self._clock() if now is None else now
        if entry.expires_at <= instant:
            self._entries.pop(handle, None)
            raise KernelError(_expired_error())
        return entry.context

    def revoke(self, handle: str) -> bool:
        return self._entries.pop(handle, None) is not None

    def purge_expired(self, *, now: float | None = None) -> int:
        instant = self._clock() if now is None else now
        stale = [h for h, e in self._entries.items() if e.expires_at <= instant]
        for h in stale:
            self._entries.pop(h, None)
        return len(stale)

    def __len__(self) -> int:
        return len(self._entries)

    def _evict_if_needed(self) -> None:
        self.purge_expired()
        while len(self._entries) >= self._max_handles:
            oldest = min(self._entries.items(), key=lambda kv: kv[1].expires_at)[0]
            self._entries.pop(oldest, None)


def _unminted_error() -> BlockError:
    return permission_denied(
        "invocation context is not minted by a trusted entry point")


def _expired_error() -> BlockError:
    error = permission_denied("invocation context has expired")
    return BlockError(
        code=error.code,
        message=error.message,
        retryable=False,
        category=error.category,
        safe_details=error.safe_details,
        recovery_action="re-establish a trusted entry context and retry the request",
        related_refs=error.related_refs,
    )


def _require_handle_syntax(handle: str) -> None:
    if not isinstance(handle, str) or not handle or len(handle) > HANDLE_PATTERN_MAX:
        raise ValueError("invocation handle violates the envelope id pattern")
    if not handle[0].isalnum():
        raise ValueError("invocation handle must start alphanumeric")
    if any(c not in "._:-" and not c.isalnum() for c in handle):
        raise ValueError("invocation handle contains an illegal character")


def coerce_machine_context(value: Any) -> MachineContext | None:
    """Accept a P10 context, a ``(principal, capabilities)`` tuple, or None.

    The tuple form keeps compatibility with composition roots that already mint
    plain tuples; anything else is treated as unminted rather than trusted.
    """
    if value is None:
        return None
    if isinstance(value, MachineContext):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        principal, capabilities = value
        if isinstance(principal, str) and principal:
            return MachineContext(handle_id="", principal_id=principal,
                                  capabilities=frozenset(capabilities or ()))
    return None


def resolve_context(resolver: Callable[[str], Any], handle: str) -> MachineContext:
    """Resolve *handle* through *resolver*, raising PERMISSION_DENIED if absent."""
    if resolver is None:
        raise KernelError(_unminted_error())
    try:
        value = resolver(handle)
    except KernelError:
        raise
    except Exception as exc:  # a broken resolver must not become a silent allow
        raise KernelError(permission_denied(
            f"invocation context could not be resolved: {type(exc).__name__}"))
    context = coerce_machine_context(value)
    if context is None:
        raise KernelError(_unminted_error())
    return context


def strip_invocation_context(params: Mapping[str, Any]) -> dict[str, Any]:
    """Copy *params* without the handle, so it cannot reach payload/hash/logs."""
    return {k: v for k, v in params.items() if k != INVOCATION_CONTEXT_FIELD}


def current_machine_context() -> MachineContext | None:
    """The trusted context of the request being handled, if any."""
    return CURRENT_MACHINE_CONTEXT.get()


def sanitize_for_log(value: Any) -> Any:
    """Drop handle-bearing fields anywhere in a nested structure."""
    if isinstance(value, Mapping):
        return {k: sanitize_for_log(v) for k, v in value.items()
                if k != INVOCATION_CONTEXT_FIELD}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_log(v) for v in value]
    return value
