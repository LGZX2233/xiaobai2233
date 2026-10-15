"""start/poll ExecutorPort adapter that drives an external solver subprocess.

Demo-grade: directory_only isolation (not an OS sandbox). A poll timeout is
reported as "unknown" and the process is left alone; reconcile observes it
again and never launches a second run.
"""
from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone

from project_kernel.contracts.dto import ExecutionHandle, ExecutionOutcome, ProviderCapabilities

PROVIDER_ID = "heat-inverse-subprocess"


class HeatInverseExecutor:
    def __init__(self, store, command_map: dict[str, list[str]], poll_timeout: float = 20.0):
        self.store = store
        self.command_map = command_map
        self.poll_timeout = poll_timeout
        self.launches = 0
        self._procs: dict[str, subprocess.Popen] = {}

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=PROVIDER_ID, supported_actions=("run",),
            supported_sandbox_level="directory_only", can_cancel=True,
            can_query_effect=True, idempotent_apply=False, external_fencing=False,
            durable_result=True, model_usage_available=False)

    def start(self, packet_ref, operation, root_ref, scope, epoch) -> ExecutionHandle:
        argv = self.command_map[operation["strategy_id"]]
        cwd = self.store.get_revision(root_ref)["payload"]["path"]
        proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.launches += 1
        run_id = "run-" + uuid.uuid4().hex[:12]
        self._procs[run_id] = proc
        return ExecutionHandle(
            execution_handle_id="exh-" + run_id, provider_id=PROVIDER_ID,
            provider_run_id=run_id, attempt_id=operation["attempt_id"],
            operation_id=operation["attempt_id"], epoch=epoch,
            started_at=datetime.now(timezone.utc).isoformat())

    def _outcome(self, scope, handle, status, code=None) -> ExecutionOutcome:
        return ExecutionOutcome(handle=handle, status=status, evidence_mode=scope.mode, exit_code=code)

    def poll(self, scope, handle) -> ExecutionOutcome:
        proc = self._procs[handle.provider_run_id]
        try:
            code = proc.wait(timeout=self.poll_timeout)
        except subprocess.TimeoutExpired:
            return self._outcome(scope, handle, "unknown")
        return self._outcome(scope, handle, "completed" if code == 0 else "failed", code)

    def reconcile(self, scope, handle) -> ExecutionOutcome:
        proc = self._procs[handle.provider_run_id]
        code = proc.poll()
        if code is None:
            return self._outcome(scope, handle, "unknown")
        return self._outcome(scope, handle, "completed" if code == 0 else "failed", code)

    def cancel(self, scope, handle, reason) -> ExecutionOutcome:
        proc = self._procs[handle.provider_run_id]
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        return self._outcome(scope, handle, "cancelled", proc.returncode)

    def close(self) -> None:
        for proc in self._procs.values():
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
