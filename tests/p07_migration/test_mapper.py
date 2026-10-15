"""Acceptance #3/#4: mapper idempotency, classification, raw retention."""
from __future__ import annotations

from project_kernel.migration.legacy import (
    Classification,
    LegacyMapper,
    LegacyReader,
    derive_object_id,
)

from .helpers import PROJECT_MAPPING, make_legacy_source


def _facts(source, mapping=PROJECT_MAPPING):
    records = LegacyReader(source, "legacy-store").read()
    mapper = LegacyMapper("legacy-store", "proj-a", mapping)
    return records, mapper.map_all(records)


def test_mapping_is_deterministic_and_idempotent(tmp_path):
    source = make_legacy_source(tmp_path)
    records, facts = _facts(source)
    assert derive_object_id("legacy-store", "task", "t-1") == \
        derive_object_id("legacy-store", "task", "t-1")
    _, facts2 = _facts(source)
    assert [(f.key, f.object_id, f.classification) for f in facts] == \
        [(f.key, f.object_id, f.classification) for f in facts2]


def test_classification_matrix(tmp_path):
    source = make_legacy_source(tmp_path)
    _, facts = _facts(source)
    by = {(f.legacy_type, f.legacy_id): f.classification for f in facts}
    # a-orphan references t-not-found -> orphan; e-orphan references a-missing -> orphan
    assert by[("attempt", "a-orphan")] == Classification.ORPHAN
    assert by[("evidence", "e-orphan")] == Classification.ORPHAN
    # t-3 belongs to p-missing which is not in the mapping -> unowned
    assert by[("task", "t-3")] == Classification.UNOWNED
    # healthy records are ok
    assert by[("task", "t-1")] == Classification.OK
    assert by[("attempt", "a-1")] == Classification.OK
    assert by[("approval", "ap-1")] == Classification.OK


def test_raw_fields_are_retained(tmp_path):
    source = make_legacy_source(tmp_path)
    records, facts = _facts(source)
    by_key = {f.key: f for f in facts}
    rec_by_key = {f"{r.legacy_type}\x1f{r.legacy_id}": r for r in records}
    for f in facts:
        assert f.raw == rec_by_key[f"{f.legacy_type}\x1f{f.legacy_id}"].raw


def test_same_display_name_projects_are_not_merged(tmp_path):
    source = make_legacy_source(tmp_path)
    records, facts = _facts(source)
    projects = [f for f in facts if f.legacy_type == "project"]
    # both legacy projects are named "Alpha" but remain distinct identities
    names = {r.raw["display_name"] for r in records if r.legacy_type == "project"}
    assert names == {"Alpha"}
    assert len(projects) == 2
    assert len({f.object_id for f in projects}) == 2
