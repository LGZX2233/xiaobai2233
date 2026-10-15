"""Frozen v1 error model.

Error carries code/message/retryable/category/safe_details/recovery_action/
related_refs; state decisions never use free text. safe_details excludes
credentials, trusted handles and unauthorized cross-project content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .enums import ErrorCategory, ErrorCode


@dataclass(frozen=True)
class SafeDetail:
    key: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "value": self.value}


@dataclass(frozen=True)
class BlockError:
    code: str
    message: str
    retryable: bool = False
    category: str = ErrorCategory.BUSINESS.value
    safe_details: tuple[SafeDetail, ...] = ()
    recovery_action: str = ""
    related_refs: tuple[Any, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "category": self.category,
            "safe_details": [d.to_dict() for d in self.safe_details],
            "recovery_action": self.recovery_action,
            "related_refs": [r.to_dict() if hasattr(r, "to_dict") else r for r in self.related_refs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlockError":
        return cls(
            code=data["code"],
            message=data["message"],
            retryable=data.get("retryable", False),
            category=data.get("category", ErrorCategory.BUSINESS.value),
            safe_details=tuple(SafeDetail(d["key"], d["value"]) for d in data.get("safe_details", [])),
            recovery_action=data.get("recovery_action", ""),
            related_refs=tuple(data.get("related_refs", [])),
        )

    def as_exception(self) -> "KernelError":
        return KernelError(self)


class KernelError(Exception):
    """Business/contract error raised by services; carries a stable BlockError."""

    def __init__(self, error: BlockError):
        super().__init__(f"{error.code}: {error.message}")
        self.error = error


def _err(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool = False,
    category: str = ErrorCategory.BUSINESS.value,
    details: Iterable[SafeDetail] = (),
    recovery_action: str = "",
    related_refs: Iterable[Any] = (),
) -> BlockError:
    return BlockError(
        code=code.value,
        message=message,
        retryable=retryable,
        category=category,
        safe_details=tuple(details),
        recovery_action=recovery_action,
        related_refs=tuple(related_refs),
    )


def invalid_input(message: str) -> BlockError:
    return _err(ErrorCode.INVALID_INPUT, message, category=ErrorCategory.INPUT.value)


def unsupported_protocol(message: str) -> BlockError:
    return _err(ErrorCode.UNSUPPORTED_PROTOCOL, message, category=ErrorCategory.INPUT.value)


def unsupported_command(message: str) -> BlockError:
    return _err(ErrorCode.UNSUPPORTED_COMMAND, message, category=ErrorCategory.INPUT.value)


def scope_required() -> BlockError:
    return _err(ErrorCode.SCOPE_REQUIRED, "An explicit project scope is required",
                category=ErrorCategory.PERMISSION.value)


def scope_mismatch(message: str) -> BlockError:
    return _err(ErrorCode.SCOPE_MISMATCH, message, category=ErrorCategory.PERMISSION.value)


def reference_not_found(message: str) -> BlockError:
    return _err(ErrorCode.REFERENCE_NOT_FOUND, message, category=ErrorCategory.INPUT.value)


def permission_denied(message: str) -> BlockError:
    return _err(ErrorCode.PERMISSION_DENIED, message, category=ErrorCategory.PERMISSION.value)


def human_identity_unavailable() -> BlockError:
    return _err(ErrorCode.HUMAN_IDENTITY_UNAVAILABLE,
                "No verified human identity is available for this action",
                category=ErrorCategory.PERMISSION.value)


def stale_revision(message: str = "Concurrent modification detected") -> BlockError:
    return _err(ErrorCode.STALE_REVISION, message, category=ErrorCategory.CONFLICT.value)


def idempotency_conflict(message: str) -> BlockError:
    return _err(ErrorCode.IDEMPOTENCY_CONFLICT, message, category=ErrorCategory.CONFLICT.value)


def capability_unavailable(message: str) -> BlockError:
    return _err(ErrorCode.CAPABILITY_UNAVAILABLE, message, category=ErrorCategory.INFRASTRUCTURE.value)


def required_fact_unknown(message: str) -> BlockError:
    return _err(ErrorCode.REQUIRED_FACT_UNKNOWN, message, category=ErrorCategory.BUSINESS.value)


def verification_failed(message: str) -> BlockError:
    return _err(ErrorCode.VERIFICATION_FAILED, message, category=ErrorCategory.BUSINESS.value)


def evidence_stale(message: str) -> BlockError:
    return _err(ErrorCode.EVIDENCE_STALE, message, category=ErrorCategory.BUSINESS.value)


def simulation_evidence() -> BlockError:
    return _err(ErrorCode.SIMULATION_EVIDENCE,
                "Simulated/test evidence cannot be treated as production evidence",
                category=ErrorCategory.BUSINESS.value)


def approval_required() -> BlockError:
    return _err(ErrorCode.APPROVAL_REQUIRED, "A valid human approval is required",
                category=ErrorCategory.BUSINESS.value)


def approval_invalid(message: str) -> BlockError:
    return _err(ErrorCode.APPROVAL_INVALID, message, category=ErrorCategory.BUSINESS.value)


def snapshot_changed() -> BlockError:
    return _err(ErrorCode.SNAPSHOT_CHANGED,
                "Decisive inputs changed; a new request is required",
                category=ErrorCategory.CONFLICT.value)


def source_conflict(message: str) -> BlockError:
    return _err(ErrorCode.SOURCE_CONFLICT, message, category=ErrorCategory.CONFLICT.value)


def source_gap(message: str) -> BlockError:
    return _err(ErrorCode.SOURCE_GAP, message, category=ErrorCategory.CONFLICT.value)


def artifact_missing(message: str) -> BlockError:
    return _err(ErrorCode.ARTIFACT_MISSING, message, category=ErrorCategory.BUSINESS.value)


def artifact_digest_mismatch(message: str) -> BlockError:
    return _err(ErrorCode.ARTIFACT_DIGEST_MISMATCH, message, category=ErrorCategory.CONFLICT.value)


def sqlite_busy(message: str = "Database busy") -> BlockError:
    return _err(ErrorCode.SQLITE_BUSY, message, retryable=True,
                category=ErrorCategory.INFRASTRUCTURE.value)


def temporary_unavailable(message: str) -> BlockError:
    return _err(ErrorCode.TEMPORARY_UNAVAILABLE, message, retryable=True,
                category=ErrorCategory.INFRASTRUCTURE.value)


def commit_outcome_unknown() -> BlockError:
    return _err(ErrorCode.COMMIT_OUTCOME_UNKNOWN,
                "Commit outcome unknown; query command.receipt with the original key",
                retryable=True, category=ErrorCategory.INFRASTRUCTURE.value)


def external_outcome_unknown(message: str) -> BlockError:
    return _err(ErrorCode.EXTERNAL_OUTCOME_UNKNOWN, message, retryable=True,
                category=ErrorCategory.INFRASTRUCTURE.value)


def as_of_unavailable() -> BlockError:
    return _err(ErrorCode.AS_OF_UNAVAILABLE,
                "Requested as_of watermark is not available; do not substitute a newer watermark",
                category=ErrorCategory.INFRASTRUCTURE.value)


def migration_checksum_mismatch(message: str) -> BlockError:
    return _err(ErrorCode.MIGRATION_CHECKSUM_MISMATCH, message,
                category=ErrorCategory.INFRASTRUCTURE.value)


def schema_incompatible(message: str) -> BlockError:
    return _err(ErrorCode.SCHEMA_INCOMPATIBLE, message,
                category=ErrorCategory.INFRASTRUCTURE.value)


def archive_partial(message: str) -> BlockError:
    return _err(ErrorCode.ARCHIVE_PARTIAL, message, category=ErrorCategory.BUSINESS.value)


def cancel_pending(message: str = "Cancellation requested but not yet confirmed") -> BlockError:
    return _err(ErrorCode.CANCEL_PENDING, message, category=ErrorCategory.BUSINESS.value)
