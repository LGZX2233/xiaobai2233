"""Command envelope hashing and receipt-domain mapping (design 04 §3/§9).

``input_hash`` covers exactly command + canonical selector IDs + expected_heads +
the strict domain payload. It deliberately excludes the JSON-RPC id, the
``invocation_context_id`` handle and any clock value, so a retry with the same
key and the same intent reuses the original receipt while a minted handle can
never influence idempotency.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ...contracts.digest import sha256_digest

#: selector may only carry candidate object IDs (command-envelope schema).
SELECTOR_ID_KEYS: tuple[str, ...] = (
    "project_id", "workspace_id", "session_id", "task_id", "attempt_id",
)

#: Shared identity domain receipts (04 §9); everything else is the project domain.
IDENTITY_RECEIPT_DOMAIN_COMMANDS: frozenset[str] = frozenset({
    "project.provision",
    "project.reconcile",
})


def canonical_selector(selector: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize a selector to its candidate IDs, in a fixed key order."""
    if not selector:
        return {}
    if not isinstance(selector, Mapping):
        raise ValueError("selector must be an object")
    return {key: selector[key] for key in SELECTOR_ID_KEYS
            if isinstance(selector.get(key), str) and selector[key]}


def canonical_expected_heads(expected_heads: Iterable[Any] | None) -> list[Any]:
    """Expected heads keep their semantic order (arrays are never sorted)."""
    if not expected_heads:
        return []
    return list(expected_heads)


def compute_input_hash(command: str, selector: Mapping[str, Any] | None,
                       expected_heads: Iterable[Any] | None,
                       payload: Any) -> str:
    """The idempotency input hash; never includes the handle or RPC id."""
    return sha256_digest({
        "command": command,
        "selector": canonical_selector(selector),
        "expected_heads": canonical_expected_heads(expected_heads),
        "payload": payload,
    })


def receipt_domain_for(command: str) -> str:
    """``identity`` for provisioning commands, ``project`` for the rest."""
    return "identity" if command in IDENTITY_RECEIPT_DOMAIN_COMMANDS else "project"
