"""Cross-check schemas, command/query catalog and strict payload coverage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_kernel.contracts import (
    ALL_COMMAND_NAMES,
    ALL_QUERY_NAMES,
    ValidationError,
    validate_command_envelope,
    validate_command_payload,
    validate_delivery_snapshot_body,
    validate_initialize_request,
    validate_initialize_result,
    validate_query_envelope,
    validate_query_payload,
)

V1 = Path(__file__).resolve().parents[2] / "contracts" / "v1"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "contracts"


def _load(name: str):
    with open(V1 / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_examples():
    with open(FIXTURES / "examples.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _payload_branches(schema):
    # oneOf branches each carry {"command": {"const": ...}, "payload": {...}}
    branches = {}
    for branch in schema["oneOf"]:
        props = branch["properties"]
        const = props["command"]["const"]
        branches[const] = props["payload"]
    return branches


def test_all_schema_files_load_as_json():
    assert (V1 / "common.schema.json").exists()
    for p in V1.glob("*.schema.json"):
        data = _load(p.name)
        assert "$id" in data, p.name


def test_catalog_and_envelope_command_names_match():
    catalog = set(c["name"] for c in _load("command-catalog.json")["commands"])
    envelope_enum = set(_load("command-envelope.schema.json")["properties"]["params"]
                        ["properties"]["command"]["enum"])
    assert catalog == envelope_enum == set(ALL_COMMAND_NAMES)
    assert len(ALL_COMMAND_NAMES) == 44


def test_catalog_and_envelope_query_names_match():
    catalog = set(q["name"] for q in _load("command-catalog.json")["queries"])
    envelope_enum = set(_load("query-envelope.schema.json")["properties"]["params"]
                        ["properties"]["query"]["enum"])
    assert catalog == envelope_enum == set(ALL_QUERY_NAMES)
    assert len(ALL_QUERY_NAMES) == 14


def test_every_command_has_strict_payload():
    branches = _payload_branches(_load("command-payloads.schema.json"))
    assert set(branches) == set(ALL_COMMAND_NAMES)
    for name, payload_schema in branches.items():
        assert payload_schema.get("additionalProperties") is False, name
        assert payload_schema.get("type") == "object", name


def test_every_query_has_strict_payload():
    branches = {}
    for branch in _load("query-payloads.schema.json")["oneOf"]:
        props = branch["properties"]
        branches[props["query"]["const"]] = props["payload"]
    assert set(branches) == set(ALL_QUERY_NAMES)
    for name, payload_schema in branches.items():
        assert payload_schema.get("additionalProperties") is False, name


def test_examples_valid_commands_and_queries_pass():
    ex = _load_examples()
    for msg in ex["valid_commands"]:
        validate_command_envelope(msg)
        p = msg["params"]
        validate_command_payload(p["command"], p["payload"])
    for msg in ex["valid_queries"]:
        validate_query_envelope(msg)
        p = msg["params"]
        validate_query_payload(p["query"], p["payload"])
    validate_initialize_request(ex["valid_initialize_request"])
    validate_initialize_result(ex["valid_initialize_result"])
    validate_delivery_snapshot_body(ex["valid_snapshot_body"])


def test_caller_cannot_set_actor_is_rejected_at_envelope():
    ex = _load_examples()
    msg = next(m for m in ex["invalid_commands"] if m["name"] == "caller-cannot-set-actor")
    with pytest.raises(ValidationError):
        validate_command_envelope(msg["message"])


def test_undeclared_role_in_payload_is_rejected_at_payload():
    ex = _load_examples()
    msg = next(m for m in ex["invalid_commands"] if m["name"] == "undeclared-role-in-payload")
    # envelope passes (no actor field at envelope level) ...
    validate_command_envelope(msg["message"])
    p = msg["message"]["params"]
    # ... but the payload layer rejects the undeclared `role` field.
    with pytest.raises(ValidationError):
        validate_command_payload(p["command"], p["payload"])


def test_payload_cannot_pass_role_or_root():
    # task.create payload declares only title/goal/requirement_refs/mode.
    base = {"title": "t", "goal": "g", "requirement_refs": [], "mode": "test"}
    validate_command_payload("task.create", dict(base))
    with pytest.raises(ValidationError):
        validate_command_payload("task.create", {**base, "role": "approver"})
    with pytest.raises(ValidationError):
        validate_command_payload("task.create", {**base, "root": "C:\\"})


def test_unknown_command_rejected_by_envelope():
    ex = _load_examples()
    msg = json.loads(json.dumps(ex["valid_commands"][0]))
    msg["params"]["command"] = "not.a.command"
    with pytest.raises(ValidationError):
        validate_command_envelope(msg)


def test_amount_and_seq_are_strings():
    from project_kernel.contracts import Amount, Cursor, sha256_digest
    a = Amount(value="9007199254740993", unit="tokens")
    assert a.value == "9007199254740993"
    c = Cursor(commit_seq="9007199254740993", event_index=0)
    assert c.commit_seq == "9007199254740993"
    assert len(sha256_digest({"x": "1"})) == 64
