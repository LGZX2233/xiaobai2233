"""Frozen v1 enums.

Single source of truth for command/query names, capabilities, phases, states and
error codes. Generated from contracts/v1 (command-catalog.json, command-envelope
and common schemas). Do not hand-edit divergently from the schemas; changes go
through P00 and docs/changes.
"""
from __future__ import annotations

from enum import Enum


class CommandName(str, Enum):
    PROJECT_PROVISION = "project.provision"
    PROJECT_RECONCILE = "project.reconcile"
    PROJECT_BIND = "project.bind"
    REQUIREMENT_SAVE = "requirement.save"
    REQUIREMENT_CONFIRM = "requirement.confirm"
    DESIGN_SAVE = "design.save"
    DISPATCH_DRAFT = "dispatch.draft"
    DISPATCH_CONFIRM = "dispatch.confirm"
    DISPATCH_REVOKE = "dispatch.revoke"
    ATTEMPT_START = "attempt.start"
    ATTEMPT_CANCEL = "attempt.cancel"
    ATTEMPT_SETTLE = "attempt.settle"
    ATTEMPT_SELECT = "attempt.select"
    VERIFICATION_RUN = "verification.run"
    DELIVERY_REQUEST = "delivery.request"
    APPROVAL_DECIDE = "approval.decide"
    DELIVERY_APPLY = "delivery.apply"
    DELIVERY_RECONCILE = "delivery.reconcile"
    TASK_CLOSE = "task.close"
    TASK_TERMINATE = "task.terminate"
    ARTIFACT_REGISTER = "artifact.register"
    ARCHIVE_EXPORT = "archive.export"
    ARCHIVE_REPAIR = "archive.repair"
    BACKUP_CREATE = "backup.create"
    RESTORE_PLAN = "restore.plan"
    RESTORE_APPLY = "restore.apply"
    SOURCE_INGEST = "source.ingest"
    LEGACY_IMPORT = "legacy.import"
    RULES_PUBLISH = "rules.publish"
    KNOWLEDGE_RECORD_USE = "knowledge.record_use"
    KNOWLEDGE_RECORD_OUTCOME = "knowledge.record_outcome"
    KNOWLEDGE_PROMOTE = "knowledge.promote"
    DATASET_BUILD = "dataset.build"
    DATASET_EXPORT = "dataset.export"
    ARTIFACTS_PLAN_CLEANUP = "artifacts.plan_cleanup"
    TASK_CREATE = "task.create"
    DESIGN_CONFIRM = "design.confirm"
    RULES_SAVE = "rules.save"
    ENVIRONMENT_PROBE = "environment.probe"
    APPROVAL_REVOKE = "approval.revoke"
    VERIFICATION_RECORD_REVIEW = "verification.record_review"
    DECISION_RECORD = "decision.record"
    DATASET_REVIEW = "dataset.review"
    RULES_PREVIEW = "rules.preview"


ALL_COMMAND_NAMES: tuple[str, ...] = tuple(c.value for c in CommandName)


class QueryName(str, Enum):
    PROJECT_OVERVIEW = "project.overview"
    PROJECT_TIMELINE = "project.timeline"
    PROJECT_TRACE = "project.trace"
    REQUIREMENTS_COVERAGE = "requirements.coverage"
    ATTEMPTS_COMPARE = "attempts.compare"
    APPROVALS_QUEUE = "approvals.queue"
    ENVIRONMENT_REPORT = "environment.report"
    ARCHIVE_STATUS = "archive.status"
    COMMAND_RECEIPT = "command.receipt"
    OPERATION_STATUS = "operation.status"
    EVENTS_READ = "events.read"
    CONTEXT_RESOLVE = "context.resolve"
    KNOWLEDGE_SEARCH = "knowledge.search"
    DATASET_PREVIEW = "dataset.preview"


ALL_QUERY_NAMES: tuple[str, ...] = tuple(q.value for q in QueryName)


class Capability(str, Enum):
    """Minimal capability set. Roles are capability collections granted by a
    trusted deployment/project mapping, never by business payload."""

    PROJECT_READ = "project.read"
    DESIGN_WRITE = "design.write"
    DISPATCH_CONFIRM = "dispatch.confirm"
    ATTEMPT_EXECUTE = "attempt.execute"
    VERIFICATION_REVIEW = "verification.review"
    APPROVAL_DECIDE = "approval.decide"
    DELIVERY_APPLY = "delivery.apply"
    RULES_PUBLISH = "rules.publish"
    KNOWLEDGE_SHARE = "knowledge.share"
    DATASET_EXPORT = "dataset.export"
    PROJECT_ADMIN = "project.admin"
    SYSTEM_INGEST = "system.ingest"


ALL_CAPABILITIES: tuple[str, ...] = tuple(c.value for c in Capability)


class TaskPhase(str, Enum):
    DRAFT = "draft"
    DESIGNING = "designing"
    DISPATCH_READY = "dispatch_ready"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    DELIVERY_READY = "delivery_ready"
    APPROVAL_PENDING = "approval_pending"
    DELIVERING = "delivering"
    CLOSED = "closed"


class TerminalOutcome(str, Enum):
    DELIVERED = "delivered"
    TERMINATED = "terminated"
    CANCELLED = "cancelled"


class AttemptStatus(str, Enum):
    PLANNED = "planned"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class Validity(str, Enum):
    CURRENT = "current"
    STALE = "stale"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class DeliveryState(str, Enum):
    PREPARED = "prepared"
    CLAIMED = "claimed"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    UNKNOWN = "unknown"


class EffectStatus(str, Enum):
    APPLIED = "applied"
    ABSENT_PENDING = "absent_pending"
    ABSENT_FINAL = "absent_final"
    UNKNOWN = "unknown"


class ArchiveSinkState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ArchiveOverall(str, Enum):
    EXPORT_PENDING = "export_pending"
    PARTIAL = "partial"
    COMPLETE = "complete"


class BlockerState(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class ReceiptStatus(str, Enum):
    COMMITTED = "committed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ReceiptDomain(str, Enum):
    IDENTITY = "identity"
    PROJECT = "project"


class Mode(str, Enum):
    PRODUCTION = "production"
    TEST = "test"


class EvidenceMode(str, Enum):
    PRODUCTION = "production"
    TEST = "test"


class BindingKind(str, Enum):
    ROOT = "root"
    WORKSPACE = "workspace"
    SESSION = "session"


class PointerName(str, Enum):
    DRAFT = "draft"
    CURRENT = "current"


class EvidenceType(str, Enum):
    AUTOMATED_TEST = "automated_test"
    HUMAN_REVIEW = "human_review"
    ARTIFACT_CHECK = "artifact_check"


class AmountUnit(str, Enum):
    USD = "USD"
    CNY = "CNY"
    TOKENS = "tokens"
    SECONDS = "seconds"


class SandboxLevel(str, Enum):
    NONE = "none"
    DIRECTORY_ONLY = "directory_only"
    PARTIAL = "partial"
    OS_ENFORCED = "os_enforced"
    UNKNOWN = "unknown"


class DeliveryMethod(str, Enum):
    BUNDLE = "bundle"


class RuleEffect(str, Enum):
    DENY = "deny"
    REQUIRE_HUMAN = "require_human"
    WARN = "warn"


class ErrorCategory(str, Enum):
    INPUT = "input"
    PERMISSION = "permission"
    CONFLICT = "conflict"
    BUSINESS = "business"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    UNSUPPORTED_COMMAND = "UNSUPPORTED_COMMAND"
    SCOPE_REQUIRED = "SCOPE_REQUIRED"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    HUMAN_IDENTITY_UNAVAILABLE = "HUMAN_IDENTITY_UNAVAILABLE"
    STALE_REVISION = "STALE_REVISION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    REQUIRED_FACT_UNKNOWN = "REQUIRED_FACT_UNKNOWN"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    SIMULATION_EVIDENCE = "SIMULATION_EVIDENCE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    SNAPSHOT_CHANGED = "SNAPSHOT_CHANGED"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SOURCE_GAP = "SOURCE_GAP"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_DIGEST_MISMATCH = "ARTIFACT_DIGEST_MISMATCH"
    SQLITE_BUSY = "SQLITE_BUSY"
    TEMPORARY_UNAVAILABLE = "TEMPORARY_UNAVAILABLE"
    COMMIT_OUTCOME_UNKNOWN = "COMMIT_OUTCOME_UNKNOWN"
    EXTERNAL_OUTCOME_UNKNOWN = "EXTERNAL_OUTCOME_UNKNOWN"
    AS_OF_UNAVAILABLE = "AS_OF_UNAVAILABLE"
    MIGRATION_CHECKSUM_MISMATCH = "MIGRATION_CHECKSUM_MISMATCH"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    ARCHIVE_PARTIAL = "ARCHIVE_PARTIAL"
    CANCEL_PENDING = "CANCEL_PENDING"


class ResultSourceKind(str, Enum):
    SESSION_EVENT = "session_event"
    PROVIDER_RESULT = "provider_result"


class UseKind(str, Enum):
    RETRIEVED = "retrieved"
    INJECTED = "injected"
    ADOPTED = "adopted"
