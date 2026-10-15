"""Pure archive completeness rules (P04).

`overall` is computed from the required sinks of the final ArchiveManifest: a
closed task with unfinished exports shows `export_pending`/`partial` and must
never claim `complete`. An unconfirmed required source flush also forbids
`complete`.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from ...contracts import ArchiveOverall, ArchiveSinkState

#: sink states that no longer make progress on their own
_TERMINAL_FAILURE = (ArchiveSinkState.FAILED.value, ArchiveSinkState.UNKNOWN.value)


def archive_overall(required_sinks: Iterable[str], sink_states: Mapping[str, str], *,
                    source_flushed: bool = True) -> str:
    required = [s for s in required_sinks]
    if not required:
        return ArchiveOverall.PARTIAL.value
    states = [sink_states.get(sink) for sink in required]
    succeeded = [s for s in states if s == ArchiveSinkState.SUCCEEDED.value]
    if not succeeded:
        return ArchiveOverall.EXPORT_PENDING.value
    if len(succeeded) == len(required) and source_flushed:
        return ArchiveOverall.COMPLETE.value
    return ArchiveOverall.PARTIAL.value


def sink_is_terminal(state: str) -> bool:
    return state in (ArchiveSinkState.SUCCEEDED.value, *_TERMINAL_FAILURE)
