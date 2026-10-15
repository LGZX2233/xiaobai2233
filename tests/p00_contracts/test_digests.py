"""RFC8785 JCS + SHA-256 golden vector verification (design D13)."""
from __future__ import annotations

import json
from pathlib import Path

from project_kernel.contracts import sha256_digest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "contracts"


def _golden_vectors():
    with open(FIXTURES / "golden-digests.json", "r", encoding="utf-8") as f:
        return json.load(f)["vectors"]


def test_golden_digest_vectors_match():
    for vec in _golden_vectors():
        actual = sha256_digest(vec["value"])
        assert actual == vec["sha256"], vec["id"]


def test_jcs_sorts_keys_and_preserves_array_order():
    value = {"b": 1, "a": ["x", "y"], "c": None}
    from project_kernel.contracts import canonicalize
    assert canonicalize(value).decode("utf-8") == '{"a":["x","y"],"b":1,"c":null}'


def test_jcs_rejects_nan_and_infinity():
    import pytest
    from project_kernel.contracts import canonicalize
    with pytest.raises(Exception):
        canonicalize({"x": float("nan")})
    with pytest.raises(Exception):
        canonicalize({"x": float("inf")})


def _snapshot_body():
    return {
        "schema_version": "1.0.0",
        "canonicalization": "rfc8785",
        "evidence_mode": "test",
        "project_id": "p1",
        "task_ref": {"project_id": "p1", "object_type": "task", "object_id": "t1", "revision_id": "r1"},
        "selected_attempt_ref": {"project_id": "p1", "object_type": "attempt", "object_id": "a1", "revision_id": "r1"},
        "packet_ref": {"project_id": "p1", "object_type": "execution_packet", "object_id": "pk1", "revision_id": "r1"},
        "requirement_refs": [{"project_id": "p1", "object_type": "requirement", "object_id": "req1", "revision_id": "r1"}],
        "design_refs": [{"project_id": "p1", "object_type": "design", "object_id": "d1", "revision_id": "r1"}],
        "acceptance_refs": [{"project_id": "p1", "object_type": "acceptance", "object_id": "acc1", "revision_id": "r1"}],
        "rule_refs": [{"project_id": "p1", "object_type": "rules", "object_id": "ru1", "revision_id": "r1"}],
        "scope_ref": {"project_id": "p1", "object_type": "scope", "object_id": "s1", "revision_id": "r1"},
        "input_manifest_ref": {"project_id": "p1", "object_type": "input_manifest", "object_id": "i1", "revision_id": "r1"},
        "context_manifest_ref": {"project_id": "p1", "object_type": "context_manifest", "object_id": "c1", "revision_id": "r1"},
        "environment_ref": {"project_id": "p1", "object_type": "environment", "object_id": "e1", "revision_id": "r1"},
        "verification_refs": [{"project_id": "p1", "object_type": "verification", "object_id": "v1", "revision_id": "r1"}],
        "candidate_digest": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "delivery": {"method": "bundle", "target_ref": {"project_id": "p1", "object_type": "delivery_target", "object_id": "dt1", "revision_id": "r1"}},
        "artifacts": [{"artifact_id": "art1", "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "size_bytes": "1", "media_type": "text/plain", "required": True}],
    }


def test_snapshot_body_digest_is_stable_and_excludes_shell():
    from project_kernel.contracts import DeliverySnapshotBody, ObjectRef, ArtifactRef, sha256_digest

    body = _snapshot_body()
    d1 = sha256_digest(body)
    d2 = sha256_digest(body)
    assert d1 == d2

    dto = DeliverySnapshotBody(
        schema_version="1.0.0", canonicalization="rfc8785", evidence_mode="test",
        project_id="p1",
        task_ref=ObjectRef("p1", "task", "t1", "r1"),
        selected_attempt_ref=ObjectRef("p1", "attempt", "a1", "r1"),
        packet_ref=ObjectRef("p1", "execution_packet", "pk1", "r1"),
        requirement_refs=(ObjectRef("p1", "requirement", "req1", "r1"),),
        design_refs=(ObjectRef("p1", "design", "d1", "r1"),),
        acceptance_refs=(ObjectRef("p1", "acceptance", "acc1", "r1"),),
        rule_refs=(ObjectRef("p1", "rules", "ru1", "r1"),),
        scope_ref=ObjectRef("p1", "scope", "s1", "r1"),
        input_manifest_ref=ObjectRef("p1", "input_manifest", "i1", "r1"),
        context_manifest_ref=ObjectRef("p1", "context_manifest", "c1", "r1"),
        environment_ref=ObjectRef("p1", "environment", "e1", "r1"),
        verification_refs=(ObjectRef("p1", "verification", "v1", "r1"),),
        candidate_digest="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        delivery={"method": "bundle", "target_ref": ObjectRef("p1", "delivery_target", "dt1", "r1").to_dict()},
        artifacts=(ArtifactRef("art1", "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "1", "text/plain", True),),
    )
    # The DTO digest matches the raw body digest, and to_dict carries no shell keys.
    assert dto.digest() == d1
    assert set(dto.to_dict()) == set(body)
    assert "approval" not in dto.to_dict()
    assert "operation_id" not in dto.to_dict()
