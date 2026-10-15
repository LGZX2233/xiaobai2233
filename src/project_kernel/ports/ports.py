"""Frozen v1 service ports (Protocol definitions).

P00 generates the typed Protocol surface from design 09; providers (P01..P09)
implement these. No provider is implemented here. The domain layer depends only
on these Protocols plus stdlib, never on sqlite3/Path/subprocess/DSH directly.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from ..contracts.dto import (
    CheckResult,
    CommandContext,
    CommandReceipt,
    EffectReceipt,
    ExecutionHandle,
    ExecutionOutcome,
    FactValue,
    ObjectRef,
    ProviderCapabilities,
    ResolvedScope,
    ResultSource,
)
from ..contracts.errors import BlockError


@runtime_checkable
class PrincipalPort(Protocol):
    def resolve(self, origin: Any, selector: Any) -> ResolvedScope: ...

    def require(self, scope: ResolvedScope, capability: str, resource_ref: ObjectRef,
                human_required: bool = False) -> ResolvedScope: ...


@runtime_checkable
class IdentityPort(Protocol):
    def provision(self, scope: ResolvedScope, request: Any) -> CommandReceipt: ...

    def reconcile(self, scope: ResolvedScope, provision_request_id: str) -> CommandReceipt: ...


@runtime_checkable
class UnitOfWorkPort(Protocol):
    def execute(self, context: CommandContext, callback: Callable[["UoWRepositories"], None]) -> CommandReceipt: ...


@runtime_checkable
class UoWRepositories(Protocol):
    records: "RecordsPort"
    outbox: "OutboxPort"


@runtime_checkable
class RecordsPort(Protocol):
    def append_revision(self, uow: Any, object_identity: Any, typed_payload: Any,
                        parent_ref: ObjectRef | None, schema: str) -> ObjectRef: ...

    def publish_head(self, uow: Any, object_ref: ObjectRef, pointer: str,
                     expected_head_version: str) -> Any: ...

    def read(self, read_scope: Any, ref: ObjectRef | None = None, as_of: str | None = None,
             pointer: str | None = None) -> Any: ...


@runtime_checkable
class FlowPort(Protocol):
    def evaluate(self, current_state: Any, command: Any, fact_bundle: Any, rules: Any) -> Any: ...


@runtime_checkable
class ExecutorPort(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...

    def start(self, packet_ref: ObjectRef, operation: Any, root_ref: ObjectRef,
              scope: ResolvedScope, epoch: str) -> ExecutionHandle: ...

    def cancel(self, scope: ResolvedScope, handle: ExecutionHandle, reason: str) -> ExecutionOutcome: ...

    def poll(self, scope: ResolvedScope, handle: ExecutionHandle) -> ExecutionOutcome: ...

    def reconcile(self, scope: ResolvedScope, handle: ExecutionHandle) -> ExecutionOutcome: ...


@runtime_checkable
class EnvironmentPort(Protocol):
    def probe(self, scope: ResolvedScope, execution_root_ref: ObjectRef,
              requirement_refs: Any, recipe_refs: Any) -> Any: ...


@runtime_checkable
class VerificationPort(Protocol):
    def run(self, scope: ResolvedScope, attempt_ref: ObjectRef, candidate_manifest_ref: ObjectRef,
            acceptance_refs: Any) -> tuple[CheckResult, ...]: ...


@runtime_checkable
class ResultSinkPort(Protocol):
    def accept(self, scope: ResolvedScope, source: ResultSource, typed_result: Any,
               epoch: str) -> CommandReceipt: ...


@runtime_checkable
class ArtifactPort(Protocol):
    def stage(self, scope: ResolvedScope, trusted_stream: Any, source_ref: ObjectRef | None,
              media_type: str, retention: str) -> Any: ...

    def publish(self, scope: ResolvedScope, staged_ref: ObjectRef, digest: str,
                source_ref: ObjectRef) -> ObjectRef: ...

    def verify(self, scope: ResolvedScope, artifact_ref: ObjectRef, required: Any) -> Any: ...

    def open_read(self, scope: ResolvedScope, artifact_ref: ObjectRef) -> Any: ...


@runtime_checkable
class SnapshotPort(Protocol):
    def freeze(self, scope: ResolvedScope, body: Any, expected_heads: Any) -> CommandReceipt: ...


@runtime_checkable
class DeliveryPort(Protocol):
    def apply(self, scope: ResolvedScope, operation_id: str, snapshot_digest: str,
              epoch: str, target_ref: ObjectRef) -> EffectReceipt: ...

    def query_effect(self, scope: ResolvedScope, operation_id: str) -> EffectReceipt: ...


@runtime_checkable
class ArchivePort(Protocol):
    def export(self, scope: ResolvedScope, manifest_ref: ObjectRef, sink_id: str,
               lease_token: str) -> CommandReceipt: ...

    def repair(self, scope: ResolvedScope, manifest_ref: ObjectRef, sink_id: str,
               effect_id: str, lease_token: str) -> CommandReceipt: ...


@runtime_checkable
class BackupPort(Protocol):
    def create(self, scope: ResolvedScope, plan_ref: ObjectRef, writer_fence_token: str) -> CommandReceipt: ...

    def restore(self, scope: ResolvedScope, plan_ref: ObjectRef, writer_fence_token: str) -> CommandReceipt: ...


@runtime_checkable
class ContextPort(Protocol):
    def resolve(self, scope: ResolvedScope, request: Any, budget: Any, source_refs: Any) -> Any: ...


@runtime_checkable
class KnowledgePort(Protocol):
    def settle(self, scope: ResolvedScope, source_key: str, knowledge_revision: ObjectRef,
               verified_outcome_ref: ObjectRef) -> CommandReceipt: ...


@runtime_checkable
class DatasetPort(Protocol):
    def build(self, scope: ResolvedScope, policy_ref: ObjectRef, source_as_of: str,
              purpose_ref: ObjectRef, split_spec: Any) -> Any: ...

    def export(self, scope: ResolvedScope, reviewed_dataset_ref: ObjectRef, sink_id: str,
               human_decision_ref: ObjectRef) -> CommandReceipt: ...


@runtime_checkable
class OutboxPort(Protocol):
    def claim(self, consumer: str, effect_id: str, scope: ResolvedScope,
              lease: Any, token: str) -> Any: ...

    def ack(self, consumer: str, effect_id: str, scope: ResolvedScope, token: str) -> Any: ...


@runtime_checkable
class SourcePort(Protocol):
    def ingest(self, scope: ResolvedScope, stream: str, events: Any,
               observed_range: Any) -> CommandReceipt: ...


@runtime_checkable
class ModelPort(Protocol):
    """LLM inference port for model-assisted operations (skill generation, etc)."""
    def generate(self, prompt: str, schema: dict[str, Any] | None = None,
                 temperature: float = 0.7) -> dict[str, Any]: ...

    def embed(self, text: str) -> list[float]: ...
