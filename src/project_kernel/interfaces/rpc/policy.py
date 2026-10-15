"""Machine command surface: allowlist ∩ declared protocol surface (design 04 §1/§4).

The protocol layer must never disagree with the machine allowlist:

* a command declared in ``initialize_result.supported_commands`` but absent from
  the allowlist is a contradiction — it is refused at construction time, not
  silently honoured;
* a human-only command is refused as ``UNSUPPORTED_COMMAND`` *before* payload
  schema validation, so an unauthenticated/machine caller never learns anything
  about the payload contract of an action it may not perform at all;
* a command in the allowlist that this build did not wire is also
  ``UNSUPPORTED_COMMAND``.

``HUMAN_ONLY_COMMANDS`` is the frozen classification from design 04 §4/§9
(approval.decide/approval.revoke/decision.record/verification.record_review/
dataset.review). The composition root passes its own set so the two can never
drift; ``tests/p10_protocol`` asserts the two are identical.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ...contracts.errors import BlockError, unsupported_command

#: Commands reachable only through a trusted human entry, never via machine RPC.
HUMAN_ONLY_COMMANDS: frozenset[str] = frozenset({
    "approval.decide",
    "approval.revoke",
    "decision.record",
    "verification.record_review",
    "dataset.review",
    "knowledge.promote",
})


class ProtocolSurfaceError(ValueError):
    """A configuration contradiction that must fail loudly, never be ignored."""


@dataclass(frozen=True)
class CommandSurface:
    """Immutable description of what this server may execute."""

    allowlist: frozenset[str]
    supported: frozenset[str]
    human_only: frozenset[str] = HUMAN_ONLY_COMMANDS

    def __post_init__(self) -> None:
        unsupported = sorted(self.supported - self.allowlist)
        if unsupported:
            raise ProtocolSurfaceError(
                "supported_commands contradict the machine allowlist: "
                + ", ".join(unsupported))
        human_leak = sorted(self.supported & self.human_only)
        if human_leak:
            raise ProtocolSurfaceError(
                "supported_commands expose human-only commands: "
                + ", ".join(human_leak))
        allowlist_leak = sorted(self.allowlist & self.human_only)
        if allowlist_leak:
            raise ProtocolSurfaceError(
                "machine allowlist must not contain human-only commands: "
                + ", ".join(allowlist_leak))

    def declared(self) -> tuple[str, ...]:
        """The surface advertised in initialize_result, deterministically ordered."""
        return tuple(sorted(self.supported))

    def reject(self, command: str) -> BlockError | None:
        """Return the refusal for *command*, or None when it may proceed."""
        if command in self.human_only:
            return unsupported_command(
                f"{command} is human-only and is not served on the machine surface")
        if command not in self.allowlist:
            return unsupported_command(
                f"{command} is not in the machine command allowlist")
        if command not in self.supported:
            return unsupported_command(f"{command} is not wired on this server")
        return None

    def allows(self, command: str) -> bool:
        return self.reject(command) is None


def build_surface(*, allowlist: Iterable[str], supported_commands: Iterable[str],
                  human_only: Iterable[str] = HUMAN_ONLY_COMMANDS,
                  catalog: Iterable[str] | None = None) -> CommandSurface:
    """Assemble a surface, checking it against the allowlist and the catalog."""
    allow = frozenset(allowlist)
    supported = frozenset(supported_commands)
    human = frozenset(human_only)
    if catalog is not None:
        known = frozenset(catalog)
        unknown = sorted((allow | supported | human) - known)
        if unknown:
            raise ProtocolSurfaceError(
                "surface names commands that are not in the frozen catalog: "
                + ", ".join(unknown))
    return CommandSurface(allowlist=allow, supported=supported, human_only=human)
