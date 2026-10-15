"""TEST-ONLY subprocess Executor fixture.

Runs a pre-configured command list in a real subprocess within the given
execution root. This is NOT a product execution engine: it exists only to prove
real success / real failure / timeout-unknown semantics in isolated tests.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Any

from project_kernel.contracts.dto import ProviderCapabilities


class FixtureSubprocessExecutor:
    """TEST-ONLY provider. command_map: strategy_id -> argv list."""

    def __init__(self, command_map: dict[str, list[str]], timeout: float = 5.0,
                 cwd: str | None = None,
                 start_barrier: threading.Barrier | None = None):
        self.command_map = command_map
        self.timeout = timeout
        self.cwd = cwd
        self.start_barrier = start_barrier

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="fixture-subprocess", supported_actions=("run",),
            supported_sandbox_level="directory_only", can_cancel=False,
            can_query_effect=False, idempotent_apply=False, external_fencing=False,
            durable_result=True, model_usage_available=False)

    def run(self, strategy_id: str, execution_root: Any) -> dict[str, Any]:
        argv = self.command_map.get(strategy_id)
        if argv is None:
            return {"status": "failed", "exit_code": None,
                    "stdout": b"", "stderr": b"no such command", "execution_handle_id": None}
        if self.start_barrier is not None:
            # Bounded wait: a worker that never arrives must fail the test
            # instead of blocking every other thread forever.
            self.start_barrier.wait(timeout=30)
        cwd = execution_root if isinstance(execution_root, str) else self.cwd
        try:
            proc = subprocess.run(argv, cwd=cwd, capture_output=True,
                                  timeout=self.timeout, check=False)
            status = "completed" if proc.returncode == 0 else "failed"
            return {"status": status, "exit_code": proc.returncode,
                    "stdout": proc.stdout, "stderr": proc.stderr,
                    "execution_handle_id": f"run-{strategy_id}"}
        except subprocess.TimeoutExpired:
            return {"status": "unknown", "exit_code": None,
                    "stdout": b"", "stderr": b"timeout", "execution_handle_id": None}
