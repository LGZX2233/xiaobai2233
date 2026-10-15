"""Import boundary checks (design 01 / AC03).

The domain/contract layer must not import sqlite3/subprocess/CLI/DSH; the
package must be importable with no real provider registered.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "project_kernel"

FORBIDDEN = {
    "sqlite3",
    "subprocess",
}

# Anything that smells like a DSH / third-party host SDK.
FORBIDDEN_PREFIXES = ("dsh", "deepseek", "anthropic", "openai")


def _imports_of(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def _contract_and_port_files():
    yield from (SRC / "contracts").glob("*.py")
    yield from (SRC / "ports").glob("*.py")


def test_contracts_and_ports_have_no_banned_imports():
    for path in _contract_and_port_files():
        for mod in _imports_of(path):
            root = mod.split(".")[0]
            assert root not in FORBIDDEN, f"{path.name} imports {mod}"
            assert not root.startswith(FORBIDDEN_PREFIXES), f"{path.name} imports {mod}"


def test_package_imports_without_provider_or_dsh():
    import project_kernel  # noqa: F401
    import project_kernel.contracts  # noqa: F401
    import project_kernel.ports  # noqa: F401
    assert "project_kernel" in sys.modules


def test_ports_are_protocols():
    from project_kernel.ports import (
        PrincipalPort, UnitOfWorkPort, ExecutorPort, ArtifactPort, DeliveryPort,
    )
    assert hasattr(PrincipalPort, "resolve")
    assert hasattr(ExecutorPort, "start")
    assert hasattr(ExecutorPort, "cancel")
    assert hasattr(ArtifactPort, "stage")
    assert hasattr(ArtifactPort, "publish")
    assert hasattr(DeliveryPort, "apply")
    assert hasattr(UnitOfWorkPort, "execute")
