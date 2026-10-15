"""ContextResolver: mandatory/optional selection under a token budget.

Design 05 §1 and AC33: mandatory materials that are missing, stale/expired or
over budget block resolution with a stable error - never silently truncated.
Non-mandatory material may be pruned for budget but every prune is recorded as
an exclusion with its reason. Selection order is: identity/safety constraints,
requirements/acceptance/design, environment/errors/dependencies, task project
materials, then explicit shared experience. Cross-project material is excluded
unless it is explicit shared experience in an allowed scope.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from ..contracts.dto import ObjectRef
from ..contracts.errors import (
    BlockError,
    KernelError,
    evidence_stale,
    invalid_input,
    required_fact_unknown,
)
from .models import (
    ContextExclusion,
    ContextManifest,
    ContextRequest,
    ContextSelection,
    SourceMaterial,
)
from .token_meter import TokenMeterPort

SOURCE_KIND_PRIORITY = {
    "identity_constraint": 0,
    "safety_constraint": 0,
    "requirement": 10,
    "acceptance": 10,
    "design": 20,
    "environment": 30,
    "error": 30,
    "dependency": 30,
    "project_material": 40,
    "shared_experience": 50,
}

_SCHEMA_VERSION = "1.0.0"
_CANONICALIZATION = "rfc8785"


class RequiredFactError(KernelError):
    """Raised when a mandatory material is missing/stale/expired/over budget."""

    def __init__(self, error: BlockError):
        super().__init__(error)


class ContextResolver:
    def __init__(self, meter: TokenMeterPort):
        self.meter = meter

    def resolve(self, request: ContextRequest,
                materials: Iterable[SourceMaterial]) -> ContextManifest:
        self._validate_request(request)
        material_list = list(materials)
        by_key: dict[str, list[SourceMaterial]] = {}
        for m in material_list:
            if not isinstance(m, SourceMaterial):
                raise KernelError(invalid_input("materials must be SourceMaterial"))
            by_key.setdefault(m.key, []).append(m)

        selections: list[ContextSelection] = []
        exclusions: list[ContextExclusion] = []
        used = 0

        # 1. mandatory first: any gap blocks, no silent truncation.
        for key in sorted(request.mandatory_refs):
            candidate = self._pick_mandatory(key, by_key.get(key, []), request)
            tokens = self._tokens(request, candidate)
            selections.append(self._select(candidate, tokens))
            used += tokens

        # mandatory set alone must fit the budget; otherwise this is a blocker.
        if used > request.token_budget:
            raise RequiredFactError(required_fact_unknown(
                f"mandatory context needs {used} tokens but budget is "
                f"{request.token_budget}; refusing to truncate mandatory material"))

        # 2. optional materials by (kind priority, priority, key).
        optional = [
            m for m in material_list
            if m.key not in request.mandatory_refs
        ]
        optional.sort(key=lambda m: (
            SOURCE_KIND_PRIORITY.get(m.source_kind, 100),
            m.priority,
            m.key,
        ))
        for m in optional:
            if not self._in_scope(m, request):
                exclusions.append(ContextExclusion(
                    key=m.key, reason="cross_project_scope", source_ref=m.source_ref,
                    project_id=m.project_id))
                continue
            tokens = self._tokens(request, m)
            if used + tokens > request.token_budget:
                exclusions.append(ContextExclusion(
                    key=m.key, reason="budget_exceeded", source_ref=m.source_ref,
                    project_id=m.project_id))
                continue
            selections.append(self._select(m, tokens))
            used += tokens

        estimation = "exact" if all(s.token_mode == "exact" for s in selections) \
            else "estimated"

        selections.sort(key=lambda s: (SOURCE_KIND_PRIORITY.get(s.source_kind, 100),
                                       s.priority, s.key))
        exclusions.sort(key=lambda e: e.key)

        return ContextManifest(
            schema_version=_SCHEMA_VERSION,
            canonicalization=_CANONICALIZATION,
            project_id=request.project_id,
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            purpose=request.purpose,
            token_budget=request.token_budget,
            token_used=used,
            token_estimation=estimation,
            selections=tuple(selections),
            exclusions=tuple(exclusions),
        )

    # -- internals -----------------------------------------------------------
    def _validate_request(self, request: ContextRequest) -> None:
        # ContextRequest already validates its own invariants on construction.
        if not request.mandatory_refs:
            raise KernelError(invalid_input(
                "ContextRequest must declare at least one mandatory_ref; "
                "an empty mandatory set is a blocker, not a pass"))

    def _in_scope(self, m: SourceMaterial, request: ContextRequest) -> bool:
        if m.project_id == request.project_id:
            return True
        return (m.source_kind == "shared_experience"
                and m.project_id in request.allowed_shared_scopes)

    def _pick_mandatory(self, key: str, candidates: list[SourceMaterial],
                        request: ContextRequest) -> SourceMaterial:
        if not candidates:
            raise RequiredFactError(required_fact_unknown(
                f"mandatory material {key!r} is missing"))
        in_scope = [m for m in candidates if self._in_scope(m, request)]
        if not in_scope:
            raise RequiredFactError(required_fact_unknown(
                f"mandatory material {key!r} exists only outside the allowed scope; "
                f"refusing cross-project selection"))
        current = [m for m in in_scope if m.validity == "current"]
        if not current:
            raise RequiredFactError(evidence_stale(
                f"mandatory material {key!r} is stale; refusing to inject stale facts"))
        fresh = [m for m in current if m.freshness != "expired"]
        if not fresh:
            raise RequiredFactError(evidence_stale(
                f"mandatory material {key!r} is expired; refusing to inject expired facts"))
        # Deterministic pick: lowest priority, then key, then revision id.
        fresh.sort(key=lambda m: (m.priority, m.key, m.source_ref.revision_id))
        return fresh[0]

    def _tokens(self, request: ContextRequest, m: SourceMaterial) -> int:
        if m.token_count is not None:
            return m.token_count
        # Conservative estimate from the material's identity; never 0 for a
        # present material so an unknown meter cannot silently pass a fact.
        return max(self.meter.estimate_tokens(
            f"{m.source_kind} {m.key} {m.source_ref.object_id} "
            f"{m.source_ref.revision_id}"), 1)

    def _select(self, m: SourceMaterial, tokens: int) -> ContextSelection:
        mode = m.token_mode if m.token_count is not None else "estimated"
        return ContextSelection(
            key=m.key,
            project_id=m.project_id,
            source_ref=m.source_ref,
            source_kind=m.source_kind,
            validity=m.validity,
            freshness=m.freshness,
            token_count=tokens,
            token_mode=mode,
            priority=m.priority,
            content_digest=m.content_digest,
        )
