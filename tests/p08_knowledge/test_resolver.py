"""ContextResolver budget/source tests (AC33 + task acceptance #1/#2)."""
from __future__ import annotations

import pytest

from project_kernel.contracts.dto import ObjectRef
from project_kernel.contracts.errors import KernelError
from project_kernel.knowledge import (
    ContextRequest,
    ContextResolver,
    DeterministicTokenMeter,
    SourceMaterial,
)


def _ref(object_id: str = "r1", project_id: str = "proj-a", rev: str = "rev-1") -> ObjectRef:
    return ObjectRef(project_id, "requirement", object_id, rev)


def _mat(key: str, *, project_id: str = "proj-a", source_kind: str = "requirement",
          validity: str = "current", freshness: str = "fresh", tokens: int = 10,
          priority: int = 10, rev: str = "rev-1") -> SourceMaterial:
    return SourceMaterial(
        key=key, project_id=project_id, source_ref=_ref(key, project_id, rev),
        source_kind=source_kind, validity=validity, freshness=freshness,
        token_count=tokens, token_mode="exact", priority=priority,
        content_digest="a" * 64)


def _req(**kw) -> ContextRequest:
    base = dict(project_id="proj-a", task_id="task-1", attempt_id="att-1",
                purpose="dispatch", model_context_limit=1000, output_reserve=200,
                token_budget=500, mandatory_refs=("requirements.current",))
    base.update(kw)
    return ContextRequest(**base)


def _resolver() -> ContextResolver:
    return ContextResolver(DeterministicTokenMeter())


# --- blocking behaviour -------------------------------------------------------

def test_mandatory_missing_blocks():
    with pytest.raises(KernelError) as exc:
        _resolver().resolve(_req(), [])
    assert exc.value.error.code == "REQUIRED_FACT_UNKNOWN"


def test_mandatory_stale_blocks():
    m = _mat("requirements.current", validity="stale")
    with pytest.raises(KernelError) as exc:
        _resolver().resolve(_req(), [m])
    assert exc.value.error.code == "EVIDENCE_STALE"


def test_mandatory_expired_blocks():
    m = _mat("requirements.current", freshness="expired")
    with pytest.raises(KernelError) as exc:
        _resolver().resolve(_req(), [m])
    assert exc.value.error.code == "EVIDENCE_STALE"


def test_mandatory_over_budget_blocks_no_truncation():
    m = _mat("requirements.current", tokens=50)
    with pytest.raises(KernelError) as exc:
        _resolver().resolve(_req(token_budget=10), [m])
    assert exc.value.error.code == "REQUIRED_FACT_UNKNOWN"


def test_empty_mandatory_set_blocks():
    with pytest.raises(KernelError) as exc:
        _resolver().resolve(_req(mandatory_refs=()), [_mat("x")])
    assert exc.value.error.code == "INVALID_INPUT"


def test_budget_exceeding_available_context_blocks_at_construction():
    with pytest.raises(ValueError):
        _req(model_context_limit=500, output_reserve=100, token_budget=500)


# --- scope / cross-project leakage -------------------------------------------

def test_cross_project_material_is_excluded_not_selected():
    foreign = _mat("other-project-note", project_id="proj-b", source_kind="design")
    manifest = _resolver().resolve(_req(mandatory_refs=("requirements.current",)),
                                   [_mat("requirements.current"), foreign])
    keys = [s.key for s in manifest.selections]
    assert "other-project-note" not in keys
    assert any(e.key == "other-project-note" and e.reason == "cross_project_scope"
               for e in manifest.exclusions)


def test_shared_experience_allowed_scope_is_selected():
    shared = _mat("shared-tip", project_id="shared-store",
                  source_kind="shared_experience")
    manifest = _resolver().resolve(
        _req(allowed_shared_scopes=("shared-store",)),
        [_mat("requirements.current"), shared])
    assert any(s.key == "shared-tip" and s.project_id == "shared-store"
               for s in manifest.selections)


def test_shared_experience_outside_allowed_scope_is_excluded():
    shared = _mat("shared-tip", project_id="shared-store",
                  source_kind="shared_experience")
    manifest = _resolver().resolve(_req(), [_mat("requirements.current"), shared])
    assert all(s.key != "shared-tip" for s in manifest.selections)
    assert any(e.key == "shared-tip" and e.reason == "cross_project_scope"
               for e in manifest.exclusions)


# --- optional pruning and traceability ----------------------------------------

def test_optional_over_budget_is_excluded_with_reason():
    mandatory = _mat("requirements.current", tokens=10)
    big_optional = _mat("design-notes", source_kind="design", tokens=1000,
                        priority=5)
    small_optional = _mat("env-note", source_kind="environment", tokens=5,
                          priority=50)
    manifest = _resolver().resolve(_req(token_budget=20),
                                   [mandatory, big_optional, small_optional])
    assert [s.key for s in manifest.selections] == ["requirements.current", "env-note"]
    assert any(e.key == "design-notes" and e.reason == "budget_exceeded"
               for e in manifest.exclusions)


def test_selection_records_source_revision_and_digest():
    manifest = _resolver().resolve(_req(), [_mat("requirements.current")])
    sel = manifest.selections[0]
    assert sel.source_ref.revision_id == "rev-1"
    assert sel.source_ref.object_type == "requirement"
    assert sel.content_digest == "a" * 64
    assert sel.token_count == 10


def test_manifest_digest_is_deterministic():
    m = [_mat("requirements.current")]
    a = _resolver().resolve(_req(), m)
    b = _resolver().resolve(_req(), m)
    assert a.digest() == b.digest()
    assert len(a.digest()) == 64


def test_resolver_accepts_generator_materials():
    manifest = _resolver().resolve(
        _req(), (_mat("requirements.current") for _ in range(1)))
    assert len(manifest.selections) == 1


def test_unknown_token_count_is_estimated_and_conservative():
    m = SourceMaterial(key="requirements.current", project_id="proj-a",
                       source_ref=_ref(), source_kind="requirement",
                       token_count=None, content_digest="a" * 64)
    manifest = _resolver().resolve(_req(), [m])
    assert manifest.selections[0].token_mode == "estimated"
    assert manifest.selections[0].token_count >= 1
    assert manifest.token_estimation == "estimated"
