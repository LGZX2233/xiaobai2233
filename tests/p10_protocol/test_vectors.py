"""Cross-language golden vectors for the command input_hash (AC02/AC37, design 04 §7).

The same file is asserted by ``node --test tests/bridge/client_test.mjs``;
both languages must reproduce the digests and must agree that a minted handle
never changes them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_kernel.contracts import validate_command_payload
from project_kernel.interfaces.rpc.commands import canonical_selector, compute_input_hash

VECTORS = Path(__file__).resolve().parents[1] / "bridge" / "vectors.json"


def _load():
    with open(VECTORS, "r", encoding="utf-8") as f:
        return json.load(f)


def test_vector_file_is_present_and_shaped():
    doc = _load()
    assert doc["version"] == "1.0.0"
    assert len(doc["vectors"]) >= 4
    assert doc["handles"]["a"] != doc["handles"]["b"]


def test_every_vector_payload_is_schema_valid_and_hashes_identically():
    doc = _load()
    for vector in doc["vectors"]:
        validate_command_payload(vector["command"], vector["payload"])
        digest = compute_input_hash(vector["command"], vector["selector"],
                                    vector["expected_heads"], vector["payload"])
        assert digest == vector["input_hash"], vector["id"]


def test_semantically_ordered_expected_heads_change_the_hash():
    doc = _load()
    ordered = next(v for v in doc["vectors"] if v["reordered_hash"])
    assert ordered["reordered_hash"] != ordered["input_hash"]
    assert compute_input_hash(ordered["command"], ordered["selector"],
                              ordered["reordered_expected_heads"],
                              ordered["payload"]) == ordered["reordered_hash"]


def test_the_handle_is_not_part_of_the_hash_input():
    doc = _load()
    handles = [doc["handles"]["a"], doc["handles"]["b"], "ctx-forged-0000"]
    for vector in doc["vectors"]:
        payload_text = json.dumps(vector["payload"], ensure_ascii=False)
        for handle in handles:
            # the hash is computed from the four contract fields only
            assert compute_input_hash(vector["command"], vector["selector"],
                                      vector["expected_heads"],
                                      vector["payload"]) == vector["input_hash"]
            assert handle not in payload_text


def test_large_sequences_and_amounts_stay_strings():
    doc = _load()
    ingest = next(v for v in doc["vectors"] if v["command"] == "source.ingest")
    seqs = [e["source_seq"] for e in ingest["payload"]["events"]]
    assert all(isinstance(s, str) for s in seqs)
    assert "9007199254740993" in seqs
    assert all(int(s) > 2 ** 53 for s in seqs)


def test_selector_normalization_drops_non_candidate_keys():
    assert canonical_selector({"project_id": "p", "actor_id": "admin",
                               "workspace_id": ""}) == {"project_id": "p"}
    assert canonical_selector(None) == {}
    with pytest.raises(ValueError):
        canonical_selector(["project_id"])
