"""Composition root (P13).

Builds the protocol servers wired to the real P02/P03/P04/P06/P09 services and to
the P10 protocol boundary. The trusted principal, capabilities, invocation handle
and receipt ledger come from the deploy-time composition, never from the payload.

Two entries, per design 04:

* :func:`build_server` — the *machine* surface. It serves only the commands in
  :data:`MACHINE_COMMAND_ALLOWLIST` that are actually implemented, and it can
  never serve a human-only command.
* :func:`build_human_server` — the *trusted human* surface for
  ``approval.decide`` / ``approval.revoke`` / ``verification.record_review`` /
  ``dataset.review`` / ``decision.record`` with verified human interaction.

Registered commands enforce configured providers at execution. Missing providers
return CAPABILITY_UNAVAILABLE; omitted identity/knowledge/legacy adapters return
UNSUPPORTED_COMMAND. Corpus commands are omitted unless explicitly enabled.
See docs/acceptance/G2-round4/limitations.md for deployment and acceptance limits.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .contracts.dto import CommandContext, Cursor, ExpectedHead, ObjectRef, ResolvedScope
from .contracts.errors import (KernelError, unsupported_command, capability_unavailable,
                               invalid_input, permission_denied, scope_mismatch)
from .application.security import require_scope
from .application.environment_service import EnvironmentService
from .application.evidence_service import EvidenceService
from .application.legacy_service import LegacyImportEntry
from .application.project_service import ProjectBindingService
from .interfaces.rpc.ingest import SourceIngestBridge
from .interfaces.rpc.source_service import SourceIngestService
from .application.attempt.service import AttemptService
from .application.delivery.service import DeliveryService
from .application.design.service import DesignService
from .corpus import CorpusService
from .data.queries.service import QueryService
from .data.store.store import Store
from .evidence import ArtifactStorage, ScopedArtifactStorage
from .evidence.provider import FileEvidenceProvider
from .evidence.archive import BundleExporter
from .evidence.delivery_provider import BundleDeliveryProvider
from .internal.delivery_provider_ports import DeliveryProvider
from .interfaces.rpc.commands import compute_input_hash
from .interfaces.rpc.invocation import InvocationContextRegistry, current_machine_context
from .interfaces.rpc.policy import HUMAN_ONLY_COMMANDS
from .interfaces.rpc.protocol import Limits, ProtocolServer
from .interfaces.rpc.identity_server import build_identity_server

#: Machine callers may invoke only these commands. Human-only commands
#: (approval.decide, approval.revoke, decision.record, verification.record_review,
#: dataset.review, knowledge.promote) are intentionally absent and reachable only
#: through the separate trusted human entry, never through the machine RPC registry.
MACHINE_COMMAND_ALLOWLIST = frozenset({
    "task.create", "requirement.save", "requirement.confirm", "design.save",
    "design.confirm", "dispatch.draft", "dispatch.confirm", "dispatch.revoke",
    "attempt.start", "attempt.cancel", "attempt.settle", "verification.run",
    "delivery.request", "delivery.apply", "delivery.reconcile", "task.close",
    "task.terminate", "attempt.select", "dataset.export",
    "artifact.register", "archive.export", "archive.repair",
    "backup.create", "restore.plan", "restore.apply", "source.ingest", "legacy.import",
    "rules.save", "rules.publish", "rules.preview", "environment.probe",
    "knowledge.record_use", "knowledge.record_outcome", "dataset.build",
    "artifacts.plan_cleanup", "project.provision", "project.reconcile",
    "project.bind",
})

#: Commands this composition root really serves on the machine surface.
MACHINE_COMMANDS: tuple[str, ...] = (
    "attempt.cancel",
    "attempt.select",
    "attempt.start",
    "artifacts.plan_cleanup",
    "dataset.build",
    "dataset.export",
    "delivery.reconcile",
    "delivery.request",
    "delivery.apply",
    "environment.probe",
    "artifact.register",
    "archive.export",
    "archive.repair",
    "backup.create",
    "restore.plan",
    "restore.apply",
    "source.ingest",
    "design.save",
    "design.confirm",
    "dispatch.revoke",
    "rules.save",
    "rules.preview",
    "rules.publish",
    "attempt.settle",
    "dispatch.confirm",
    "dispatch.draft",
    "requirement.confirm",
    "requirement.save",
    "task.close",
    "task.create",
    "task.terminate",
    "verification.run",
)

#: Commands only the trusted human entry serves: the frozen human-only set.
#: ``dataset.export`` stays a *machine* command: it is authorized by an existing
#: verified human decision revision for the same digest, exactly like
#: ``delivery.apply`` is authorized by an approval.
HUMAN_ENTRY_COMMANDS: tuple[str, ...] = tuple(sorted(HUMAN_ONLY_COMMANDS))

QUERY_NAMES: tuple[str, ...] = (
    "approvals.queue",
    "archive.status",
    "attempts.compare",
    "command.receipt",
    "dataset.preview",
    "environment.report",
    "events.read",
    "operation.status",
    "project.overview",
    "project.timeline",
    "project.trace",
    "requirements.coverage",
)


COMMAND_CAPABILITIES = {row["name"]: row["capability"] for row in json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/v1/command-catalog.json").read_text(encoding="utf-8"))["commands"]}


class KernelServices:
    """The real services behind the protocol surface, bound to one project store."""

    def __init__(self, store: Store, *, mode: str = "test", executor: Any | None = None,
                 delivery_provider: DeliveryProvider | None = None,
                 bundle_exporter: BundleExporter | None = None,
                 artifact_root: Path | str | None = None,
                 dataset_sink_root: Path | str | None = None,
                 dataset_policies: Mapping[str, Any] | None = None,
                 dataset_purposes: Mapping[str, str] | None = None,
                 check_provider: Callable | None = None, enable_corpus: bool = False,
                 environment_provider=None, evidence_config: Mapping[str, Any] | None = None,
                 source_bindings: Mapping[str, Any] | None = None,
                 trusted_provider_principals: Mapping[str, Iterable[str]] | None = None,
                 legacy_config: Mapping[str, Any] | None = None,
                 identity_registry=None):
        if delivery_provider is not None and bundle_exporter is not None:
            raise ValueError("configure delivery_provider or bundle_exporter, not both")
        if bundle_exporter is not None:
            delivery_provider = BundleDeliveryProvider(bundle_exporter)
        self.store = store
        self.mode = mode
        self.executor = executor
        self.check_provider = check_provider
        self.enable_corpus = enable_corpus
        self.source_bindings=dict(source_bindings or {})
        self.trusted_provider_principals = {
            principal_id: tuple(provider_ids)
            for principal_id, provider_ids in (trusted_provider_principals or {}).items()
        }
        self.environment=EnvironmentService(store,environment_provider)
        self.design = DesignService(store)
        self.queries = QueryService(store)
        self.artifacts = (ScopedArtifactStorage(ArtifactStorage(Path(artifact_root)),
                                               project_id=store.project_id)
                          if artifact_root is not None else None)
        self.attempt = AttemptService(store, executor=executor,
            artifact_storage=self.artifacts.storage if self.artifacts is not None else None,
            trusted_result_principals=tuple(self.source_bindings),
            trusted_provider_principals=self.trusted_provider_principals)
        self.delivery = DeliveryService(
            store, provider=delivery_provider,
            artifact_storage=self.artifacts.storage if self.artifacts is not None else None)
        evidence_options = dict(evidence_config or {})
        evidence_provider = evidence_options.pop("provider", None)
        trusted_staging_principals = evidence_options.pop("trusted_staging_principals", ())
        if evidence_provider is None:
            evidence_provider = FileEvidenceProvider(
                store, artifact_storage=self.artifacts.storage if self.artifacts else None,
                **evidence_options)
        elif evidence_options:
            raise ValueError("evidence_config cannot combine provider with provider options")
        self.evidence = EvidenceService(
            store, provider=evidence_provider,
            trusted_staging_principals=trusted_staging_principals)
        self.project_binding = (ProjectBindingService(store, identity_registry)
                                if identity_registry is not None else None)
        self.legacy = None
        if legacy_config is not None:
            if mode != "test":
                raise ValueError("legacy import configuration is test-mode only")
            options = dict(legacy_config)
            try:
                snapshot_provider = options.pop("snapshot_provider")
                trusted_snapshot_producers = options.pop("trusted_snapshot_producers")
            except KeyError as exc:
                raise ValueError("legacy_config requires snapshot_provider and trusted_snapshot_producers") from exc
            if options:
                raise ValueError("legacy_config contains unsupported options")
            self.legacy = LegacyImportEntry(store, snapshot_provider=snapshot_provider,
                                           trusted_snapshot_producers=trusted_snapshot_producers)
        self.corpus = CorpusService(store, policies=dataset_policies,
                                    purposes=dataset_purposes, sink_root=dataset_sink_root,
                                    queries=self.queries)


def _request_scope(services: KernelServices, params: Mapping[str, Any], *,
                   principal: str, capabilities: frozenset[str]) -> ResolvedScope:
    resolved = current_machine_context()
    selected = params["selector"]["project_id"]
    if selected != services.store.project_id:
        raise KernelError(scope_mismatch("selector does not match the bound project store"))
    if resolved is not None:
        if resolved.project_id != selected:
            raise KernelError(scope_mismatch("invocation handle belongs to another project"))
        if services.mode != "test" and resolved.project_id is None:
            raise KernelError(permission_denied("a project-bound invocation handle is required"))
        principal = resolved.principal_id
        capabilities = frozenset(resolved.capabilities)
    else:
        raise KernelError(permission_denied("a trusted invocation context is required"))
    scope = ResolvedScope(project_id=selected, store_id=services.store.store_id,
                          principal_id=principal, capabilities=capabilities, mode=services.mode)
    require_scope(services.store, scope)
    return scope


def _trusted_request_context(services: KernelServices, params: Mapping[str, Any], command: str,
                             *, principal: str,
                             capabilities: frozenset[str]) -> CommandContext:
    scope = _request_scope(services, params, principal=principal, capabilities=capabilities)
    capability = COMMAND_CAPABILITIES.get(command)
    if command == "decision.record":
        capability = {"restore.apply": "project.admin", "knowledge.promote": "knowledge.share",
                      "dataset.export": "dataset.export"}.get(params["payload"].get("action"))
    if capability is None:
        raise KernelError(permission_denied("command has no configured capability policy"))
    require_scope(services.store, scope, capability)
    expected = tuple(ExpectedHead(ObjectRef.from_dict(e["object_ref"]), e["pointer_name"],
                                  e["expected_head_version"])
                     for e in params.get("expected_heads", ()))
    for item in expected:
        if item.object_ref.project_id != scope.project_id:
            raise KernelError(scope_mismatch("expected head belongs to another project"))
    return CommandContext(
        scope=scope, command_id="cmd-" + uuid.uuid4().hex[:12],
        idempotency_key=params["idempotency_key"],
        input_hash=compute_input_hash(command, params.get("selector"),
                                      params.get("expected_heads"), params.get("payload")),
        expected_heads=expected)


def _human_verified() -> bool:
    resolved = current_machine_context()
    return resolved is not None and bool(resolved.human_verified)


def _payload_handler(method: Callable[[CommandContext, Mapping[str, Any]], Any],
                     context: Callable[[Mapping[str, Any], str], CommandContext]
                     ) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    def handler(command: str, params: dict[str, Any]) -> dict[str, Any]:
        receipt = method(context(params, command), params["payload"])
        return {"receipt": receipt.to_dict()}

    return handler


def _machine_handlers(services: KernelServices, principal: str, capabilities: frozenset[str]
                      ) -> dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]]:
    def ctx(params: Mapping[str, Any], command: str) -> CommandContext:
        return _trusted_request_context(services, params, command, principal=principal,
                                        capabilities=capabilities)

    direct = {
        "task.create": services.design.create_task,
        "requirement.save": services.design.requirement_save,
        "requirement.confirm": services.design.requirement_confirm,
        "design.save": services.design.design_save,
        "design.confirm": services.design.design_confirm,
        "dispatch.revoke": services.design.dispatch_revoke,
        "rules.save": services.design.rules_save,
        "rules.preview": services.design.rules_preview,
        "rules.publish": services.design.rules_publish,
        "attempt.settle": services.attempt.attempt_settle,
        "delivery.request": services.delivery.delivery_request,
        "delivery.apply": services.delivery.delivery_apply,
        "environment.probe": services.environment.environment_probe,
        "artifact.register": services.evidence.artifact_register,
        "archive.export": services.evidence.archive_export,
        "archive.repair": services.evidence.archive_repair,
        "backup.create": services.evidence.backup_create,
        "restore.plan": services.evidence.restore_plan,
        "restore.apply": services.evidence.restore_apply,
        "dispatch.draft": services.design.dispatch_draft,
        "dispatch.confirm": services.design.dispatch_confirm,
        "attempt.start": services.attempt.attempt_start,
        "attempt.cancel": services.attempt.attempt_cancel,
        "dataset.build": services.corpus.build,
        "dataset.export": services.corpus.export,
        "artifacts.plan_cleanup": services.corpus.plan_cleanup,
    }
    handlers = {command: _payload_handler(method, ctx) for command, method in direct.items()}

    def decisive_publish(command: str, params: dict[str, Any]) -> dict[str, Any]:
        request_context = ctx(params, command)
        receipt = direct[command](request_context, params["payload"])
        if receipt.status == "committed":
            services.delivery.refresh_approvals(request_context)
        return {"receipt": receipt.to_dict()}

    for command in ("requirement.confirm", "design.confirm", "rules.publish"):
        handlers[command] = decisive_publish

    def attempt_select(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.select_attempt(
            ctx(params, command), payload["attempt_ref"], payload.get("comparison_refs", ()),
            payload["purpose"], payload["reason"])
        return {"receipt": receipt.to_dict()}

    def verification_run(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.verification_run(
            ctx(params, command), ObjectRef.from_dict(payload["attempt_ref"]),
            ObjectRef.from_dict(payload["candidate_manifest_ref"]),
            acceptance_refs=payload.get("acceptance_refs", ()), check_provider=services.check_provider,
            evidence_mode=services.mode)
        return {"receipt": receipt.to_dict()}

    def delivery_reconcile(command: str, params: dict[str, Any]) -> dict[str, Any]:
        receipt = services.delivery.delivery_reconcile(ctx(params, command),
                                                       params["payload"]["operation_id"])
        return {"receipt": receipt.to_dict()}

    def task_close(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.task_close(ctx(params, command), payload["task_ref"],
                                               payload["applied_operation_ref"])
        return {"receipt": receipt.to_dict()}

    def task_terminate(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.task_terminate(ctx(params, command), payload["task_ref"],
                                                   payload["outcome"], payload["reason"],
                                                   payload.get("unsettled_refs", ()))
        return {"receipt": receipt.to_dict()}

    handlers.update({
        "attempt.select": attempt_select,
        "verification.run": verification_run,
        "delivery.reconcile": delivery_reconcile,
        "task.close": task_close,
        "task.terminate": task_terminate,
    })
    def source_ingest(command, params):
        context=ctx(params,command)
        if services.artifacts is None:
            raise KernelError(capability_unavailable("source artifact storage unavailable"))
        delegate=SourceIngestService(services.store,scope_resolver=lambda request: context.scope,
            bindings=services.source_bindings,artifact_storage=services.artifacts.storage,
            trusted_provider_principals=services.trusted_provider_principals)
        return SourceIngestBridge(delegate).handle(command,params)
    handlers["source.ingest"]=source_ingest
    if services.project_binding is not None:
        handlers["project.bind"] = _payload_handler(services.project_binding.project_bind, ctx)
    if services.legacy is not None:
        handlers["legacy.import"] = _payload_handler(services.legacy.import_legacy, ctx)
    return handlers


def _human_handlers(services: KernelServices, principal: str, capabilities: frozenset[str]
                    ) -> dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]]:
    def ctx(params: Mapping[str, Any], command: str) -> CommandContext:
        return _trusted_request_context(services, params, command, principal=principal,
                                        capabilities=capabilities)

    def approval_decide(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.decide_approval(
            ctx(params, command), payload["approval_id"], payload["decision"],
            payload["snapshot_digest"], is_human=_human_verified(), reason=payload["reason"])
        return {"receipt": receipt.to_dict()}

    def approval_revoke(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.approval_revoke(
            ctx(params, command), payload["approval_id"], payload["snapshot_digest"],
            is_human=_human_verified(), reason=payload["reason"])
        return {"receipt": receipt.to_dict()}

    def verification_record_review(command: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = params["payload"]
        receipt = services.delivery.record_review(
            ctx(params, command), ObjectRef.from_dict(payload["verification_ref"]),
            payload["check_id"], payload["candidate_digest"], payload["result"],
            payload.get("evidence_refs", ()), payload["reason"], is_human=_human_verified())
        return {"receipt": receipt.to_dict()}

    def dataset_review(command: str, params: dict[str, Any]) -> dict[str, Any]:
        receipt = services.corpus.review(ctx(params, command), params["payload"],
                                         is_human=_human_verified())
        return {"receipt": receipt.to_dict()}

    def decision_record(command: str, params: dict[str, Any]) -> dict[str, Any]:
        receipt = services.delivery.decision_record(ctx(params, command), params["payload"],
                                                    is_human=_human_verified())
        return {"receipt": receipt.to_dict()}

    return {
        "approval.decide": approval_decide,
        "approval.revoke": approval_revoke,
        "verification.record_review": verification_record_review,
        "dataset.review": dataset_review,
        "decision.record": decision_record,
    }


def _query_handler(services: KernelServices, principal: str, capabilities: frozenset[str]) -> Callable[
        [str, dict[str, Any]], dict[str, Any]]:
    queries = services.queries

    def handler(query: str, params: dict[str, Any]) -> dict[str, Any]:
        scope = _request_scope(services, params, principal=principal, capabilities=capabilities)
        require_scope(services.store, scope, READ_CAPABILITY)
        payload = params["payload"]
        requested = params.get("as_of_seq")
        page = params.get("page_token")
        if page is not None and query not in {"project.timeline", "approvals.queue"}:
            raise KernelError(invalid_input(f"{query} does not support page_token"))
        with queries._read_tx():
            env = queries._envelope()
            as_of = env.resolve_as_of(requested)
            if query == "project.overview":
                return queries.project_overview(as_of_seq=as_of)
            if query == "project.timeline":
                return queries.project_timeline(payload.get("object_type"), as_of_seq=requested,
                                                page_token=page)
            if query == "project.trace":
                return queries.project_trace(payload["root_ref"], payload["direction"],
                                             payload["max_depth"], as_of_seq=as_of)
            if query == "requirements.coverage":
                return queries.requirements_coverage(payload.get("requirement_refs"), as_of_seq=as_of)
            if query == "attempts.compare":
                return queries.attempts_compare(payload["task_ref"], as_of_seq=as_of)
            if query == "approvals.queue":
                return queries.approvals_queue(payload.get("status"), as_of_seq=requested,
                                               page_token=page)
            if query == "environment.report":
                return queries.environment_report(payload["task_ref"], as_of_seq=as_of)
            if query == "archive.status":
                return queries.archive_status(payload["manifest_ref"], as_of_seq=as_of)
            if query == "command.receipt":
                if payload["receipt_domain"] != "project":
                    raise KernelError(capability_unavailable("identity receipt store is not configured"))
                data = queries.command_receipt(scope.principal_id, payload["idempotency_key"])
                if data is not None and int(data["receipt"]["commit_seq"]) > as_of:
                    data = None
            elif query == "operation.status":
                data = queries.operation_status(payload["operation_id"], as_of_seq=as_of)
            elif query == "events.read":
                after = payload["after"]
                data = queries.events_read(Cursor(str(after["commit_seq"]), int(after["event_index"])),
                                           as_of_seq=as_of, limit=int(payload["limit"]))
            elif query == "dataset.preview":
                data = services.corpus.preview(scope, payload, as_of_seq=as_of)
            else:
                raise KernelError(unsupported_command(f"query {query!r} not wired"))
            envelope = env.finalize(query, {}, as_of_seq=as_of)
            envelope["data"] = data
            return envelope

    return handler


#: Read capability required by the query surface.
READ_CAPABILITY = "project.read"


def build_server(store: Store, *, principal: str,
                 capabilities: frozenset[str] = frozenset(),
                 mode: str = "test", executor: Any | None = None,
                 delivery_provider: DeliveryProvider | None = None,
                 bundle_exporter: BundleExporter | None = None,
                 contexts: InvocationContextRegistry | None = None,
                 artifact_root: Path | str | None = None,
                 dataset_sink_root: Path | str | None = None,
                 dataset_policies: Mapping[str, Any] | None = None,
                 dataset_purposes: Mapping[str, str] | None = None,
                 receipt_ledger: Any | None = None,
                 limits: Limits | None = None,
                  check_provider: Callable | None = None,
                 enable_corpus: bool = False,
                 environment_provider=None, evidence_config: Mapping[str, Any] | None = None,
                 source_bindings: Mapping[str, Any] | None = None,
                 trusted_provider_principals: Mapping[str, Iterable[str]] | None = None,
                 legacy_config: Mapping[str, Any] | None = None,
                 identity_registry=None) -> ProtocolServer:
    """Machine entry with explicitly configured delivery effects.

    ``delivery_provider`` supplies the sink port. ``bundle_exporter`` configures
    its filesystem implementation; the two options are mutually exclusive.
    Omitting both leaves delivery application unavailable.
    """
    if contexts is None:
        raise ValueError("a trusted InvocationContextRegistry is required")
    services = KernelServices(store, mode=mode, executor=executor,
                              delivery_provider=delivery_provider,
                              bundle_exporter=bundle_exporter, artifact_root=artifact_root,
                              dataset_sink_root=dataset_sink_root,
                              dataset_policies=dataset_policies,
                              dataset_purposes=dataset_purposes, check_provider=check_provider,
                              enable_corpus=enable_corpus, environment_provider=environment_provider,
                              evidence_config=evidence_config, source_bindings=source_bindings,
                              trusted_provider_principals=trusted_provider_principals,
                              legacy_config=legacy_config, identity_registry=identity_registry)
    context_resolver = contexts.resolve if contexts is not None else None
    supported_commands = [c for c in MACHINE_COMMANDS if enable_corpus or
                          c not in {"dataset.build", "dataset.export", "artifacts.plan_cleanup"}]
    if services.project_binding is not None:
        supported_commands.append("project.bind")
    if services.legacy is not None:
        supported_commands.append("legacy.import")
    return ProtocolServer(
        mode=mode,
        supported_commands=supported_commands,
        supported_queries=[q for q in QUERY_NAMES if enable_corpus or q != "dataset.preview"],
        allowlist=MACHINE_COMMAND_ALLOWLIST,
        human_only_commands=HUMAN_ONLY_COMMANDS,
        context_resolver=context_resolver,
        receipt_ledger=receipt_ledger,
        command_authorizer=lambda command,params: {"authorized": bool(_trusted_request_context(services,params,command,principal=principal,capabilities=capabilities))},
        limits=limits,
        command_handlers=_machine_handlers(services, principal, frozenset(capabilities)),
        query_handler=_query_handler(services, principal, frozenset(capabilities)),
    )


def build_human_server(store: Store, *, principal: str,
                       capabilities: frozenset[str] = frozenset(),
                       mode: str = "test", executor: Any | None = None,
                       delivery_provider: DeliveryProvider | None = None,
                       bundle_exporter: BundleExporter | None = None,
                       contexts: InvocationContextRegistry | None = None,
                       artifact_root: Path | str | None = None,
                       dataset_sink_root: Path | str | None = None,
                       dataset_policies: Mapping[str, Any] | None = None,
                       dataset_purposes: Mapping[str, str] | None = None,
                       limits: Limits | None = None,
                  check_provider: Callable | None = None,
                 enable_corpus: bool = False,
                 environment_provider=None, evidence_config: Mapping[str, Any] | None = None,
                 source_bindings: Mapping[str, Any] | None = None,
                 trusted_provider_principals: Mapping[str, Iterable[str]] | None = None) -> ProtocolServer:
    """Trusted human entry: only the human-decision commands, never machine ones.

    Every request requires a project-bound handle from the trusted registry.
    Human decisions additionally require verified interaction evidence.
    Delivery providers use the same explicit configuration as ``build_server``.
    """
    if contexts is None:
        raise ValueError("a trusted InvocationContextRegistry is required")
    services = KernelServices(store, mode=mode, executor=executor,
                              delivery_provider=delivery_provider,
                              bundle_exporter=bundle_exporter, artifact_root=artifact_root,
                              dataset_sink_root=dataset_sink_root,
                              dataset_policies=dataset_policies,
                              dataset_purposes=dataset_purposes, check_provider=check_provider,
                              enable_corpus=enable_corpus, environment_provider=environment_provider,
                              evidence_config=evidence_config, source_bindings=source_bindings,
                              trusted_provider_principals=trusted_provider_principals)
    return ProtocolServer(
        mode=mode,
        supported_commands=[c for c in HUMAN_ENTRY_COMMANDS if enable_corpus or c != "dataset.review"],
        supported_queries=[],
        allowlist=frozenset(HUMAN_ENTRY_COMMANDS),
        human_only_commands=frozenset(),
        context_resolver=contexts.resolve if contexts is not None else None,
        limits=limits,
        command_handlers=_human_handlers(services, principal, frozenset(capabilities)),
        query_handler=None,
    )


__all__ = [
    "HUMAN_ENTRY_COMMANDS",
    "HUMAN_ONLY_COMMANDS",
    "InvocationContextRegistry",
    "KernelServices",
    "MACHINE_COMMAND_ALLOWLIST",
    "MACHINE_COMMANDS",
    "QUERY_NAMES",
    "build_human_server",
    "build_identity_server",
    "build_server",
]
