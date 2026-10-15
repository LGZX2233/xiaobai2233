"""Strict JSON Schema (2020-12) validation over the frozen contracts.

Two-layer validation, matching the design: the envelope schema validates the
JSON-RPC envelope, then {command|query, payload} is validated against the
per-command / per-query schema. Every schema uses additionalProperties=false.
$id URIs under https://project-kernel.invalid/ are resolved to local files and
never fetched over the network.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .errors import BlockError, invalid_input

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "contracts" / "v1"
_BASE = "https://project-kernel.invalid/design/v1/"


class ValidationError(ValueError):
    """Raised when a message fails schema validation; wraps a BlockError."""

    def __init__(self, error: BlockError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


def _load_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(_SCHEMA_DIR.glob("*.json")):
        if path.name == "bundle-manifest.json":
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sid = data.get("$id")
        if sid:
            schemas[sid] = data
    return schemas


_SCHEMAS: dict[str, dict[str, Any]] | None = None


def _schemas() -> dict[str, dict[str, Any]]:
    global _SCHEMAS
    if _SCHEMAS is None:
        _SCHEMAS = _load_schemas()
    return _SCHEMAS


def _registry() -> Registry:
    resources = [(uri, Resource.from_contents(schema)) for uri, schema in _schemas().items()]
    return Registry().with_resources(resources)


def _validator_for(schema: Mapping[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=_registry())


def _schema_by_name(name: str) -> dict[str, Any]:
    return _schemas()[_BASE + name]


def _validate(schema_name: str, value: Any) -> None:
    schema = _schema_by_name(schema_name)
    errors = sorted(_validator_for(schema).iter_errors(value), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        path = "/".join(str(p) for p in first.absolute_path) or "(root)"
        detail = f"{path}: {first.message}"
        raise ValidationError(invalid_input(f"{schema_name} validation failed at {detail}"))


def validate_command_envelope(value: Any) -> None:
    _validate("command-envelope.schema.json", value)


def validate_command_payload(command: str, payload: Any) -> None:
    _validate("command-payloads.schema.json", {"command": command, "payload": payload})


def validate_query_envelope(value: Any) -> None:
    _validate("query-envelope.schema.json", value)


def validate_query_payload(query: str, payload: Any) -> None:
    _validate("query-payloads.schema.json", {"query": query, "payload": payload})


def validate_initialize_request(value: Any) -> None:
    _validate("initialize-request.schema.json", value)


def validate_initialize_result(value: Any) -> None:
    _validate("initialize-result.schema.json", value)


def validate_delivery_snapshot_body(value: Any) -> None:
    _validate("delivery-snapshot.schema.json", value)


def validate_command_receipt(value: Any) -> None:
    _validate("command-receipt.schema.json", value)
