"""Shared P04 fixtures.

Every store/file lives under ``tmp_path``; nothing here writes to the CWD or to
real user data. Host-owned configuration and candidate artifact capture are seeded directly;
requirements, acceptance, packet and execution are created by their services.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from project_kernel.application.attempt.service import AttemptService
from project_kernel.application.delivery.service import DeliveryService
from project_kernel.application.design.service import DesignService
from project_kernel.contracts import ALL_CAPABILITIES, sha256_digest
from project_kernel.contracts.dto import (
    AcceptanceItem,
    CheckResult,
    CommandContext,
    ObjectRef,
    ResolvedScope,
)
from project_kernel.data.store.uow import UnitOfWork
from project_kernel.evidence.archive import BundleExporter
from project_kernel.evidence.delivery_provider import BundleDeliveryProvider
from project_kernel.evidence.artifact_store import ArtifactStorage

from p01_store.helpers import make_store
from p02_design.helpers import prepare_dispatch, seed
from p03_attempt.fixture_executor import FixtureSubprocessExecutor

PROJ = "proj-a"
ALL = frozenset(ALL_CAPABILITIES)
CANDIDATE = "b" * 64


def scope(principal: str = "human-1", caps: frozenset[str] = ALL,
          mode: str = "test") -> ResolvedScope:
    return ResolvedScope(project_id=PROJ, store_id="store-a", principal_id=principal,
                         capabilities=caps, mode=mode)


def ctx(key: str, principal: str = "human-1", caps: frozenset[str] = ALL) -> CommandContext:
    return CommandContext(scope=scope(principal, caps), command_id="cmd",
                          idempotency_key=key, input_hash=sha256_digest({"key": key}))


def oref(object_type: str, object_id: str, revision_id: str = "rev-1") -> ObjectRef:
    return ObjectRef(PROJ, object_type, object_id, revision_id)


def rdict(object_type: str, object_id: str, revision_id: str = "rev-1") -> dict[str, str]:
    return oref(object_type, object_id, revision_id).to_dict()


def seed_revision(store, object_type: str, object_id: str, payload: Any, key: str) -> ObjectRef:
    """TEST-ONLY seed of a ledger object no service creates yet."""
    created: list[ObjectRef] = []

    def cb(h):
        head = store.get_head(object_type, object_id, "current")
        r = h.records.append_revision(object_type, object_id, payload, f"{object_type}.v1")
        h.records.publish_head(r, "current",
                               expected_head_version=str(head["head_version"])
                               if head is not None else None)
        created.append(r)

    UnitOfWork(store, ctx(key, principal="seeder"), "system.ingest").execute(cb)
    return created[0]


def patch_object(store, object_type: str, object_id: str, patch: dict[str, Any], key: str):
    """TEST-ONLY: append a new revision with *patch* merged into the head payload."""
    def cb(h):
        head = store.get_head(object_type, object_id, "current")
        payload = store.get_revision(
            ObjectRef(store.project_id, object_type, object_id, head["revision_id"]))["payload"]
        r = h.records.append_revision(object_type, object_id, {**payload, **patch},
                                      f"{object_type}.v1")
        h.records.publish_head(r, "current", expected_head_version=str(head["head_version"]))

    return UnitOfWork(store, ctx(key, principal="editor"), "design.save").execute(cb)


def acceptance_item(item_id: str, *, required: bool = True,
                    evidence_type: str = "automated_test") -> dict[str, Any]:    return {"item_id": item_id,
            "requirement_ref": rdict("requirement", "req-1"),
            "recipe_ref": rdict("recipe", f"recipe-{item_id}"),
            "required": required, "evidence_type": evidence_type, "criterion": "meets it"}


class Harness:
    """Drives a real task from draft to delivery_ready through the real services."""

    def __init__(self, tmp_path: Path, *, with_executor: bool = True,
                 effect_query=None) -> None:
        self.tmp_path = tmp_path
        self.store = make_store(tmp_path, project_id=PROJ)
        self.storage = ArtifactStorage(tmp_path / "artifacts")
        self.exporter = BundleExporter(tmp_path / "exports", self.storage)
        self.provider = BundleDeliveryProvider(self.exporter, effect_query=effect_query)
        self.svc = DeliveryService(self.store, provider=self.provider,
                                   artifact_storage=self.storage)
        self.design = DesignService(self.store)
        self.attempt = AttemptService(
            self.store,
            executor=(FixtureSubprocessExecutor({"s1": [sys.executable, "-c", "print('ok')"]},
                                                cwd=str(tmp_path)) if with_executor else None), artifact_storage=self.storage)
        staged = self.storage.stage(b"deliverable content", "text/plain")
        self.artifact = self.storage.publish(staged, "text/plain")
        self.candidate = seed_revision(self.store, "candidate_manifest", "cand-1",
                                       {"candidate_digest": CANDIDATE,
                                        "artifacts": [self.artifact.to_dict()]}, "seed-cand")

    def close(self) -> None:
        self.store.close()

    # -- chain -------------------------------------------------------------
    def to_attempt(self) -> ObjectRef:
        p=prepare_dispatch(self.store,self.tmp_path)
        self.prepared=p
        self.task_ref=p["task"]
        self.packet_ref=p["packet"]
        self.acceptance_ref=p["acceptance"]
        self.scope_ref=seed(self.store,"scope","s1",p["scope"])
        self.input_ref=seed(self.store,"input_manifest","i1",{"base_content_digest":p["body"]["base_content_digest"]})
        self.context_ref=seed(self.store,"context_manifest","c1",{"refs":[p["requirement"].to_dict()]})
        self.target_ref=seed(self.store,"delivery_target","dt1",{"method":"bundle","sink_id":"exports"})
        started=self.attempt.attempt_start(ctx("a1"),{"packet_ref":self.packet_ref.to_dict(),
            "strategy_id":"s1","execution_root_ref":p["roots"]["s1"].to_dict()})
        assert started.status=="accepted",started.error
        self.attempt_ref=oref("attempt",started.operation_id,self.store.get_head("attempt",started.operation_id,"current")["revision_id"])
        return self.attempt_ref

    def verify(self, *, items: list[dict[str, Any]] | None = None,
               checks: list[Any] | None = None, evidence_mode: str = "test") -> ObjectRef:
        refs=[] if items is not None else [self.acceptance_ref]
        items = items if items is not None else []
        checks = checks if checks is not None else self._passing_checks(items or [self.prepared["item"]])
        report = self.svc.verification_run(ctx("v1"), self.attempt_ref, self.candidate,
                                          items, checks, acceptance_refs=refs, evidence_mode=evidence_mode)
        assert report.status == "committed", report.error
        self.report_ref = report.object_refs[0]
        return self.report_ref

    def to_verifying(self, **kwargs) -> dict[str, Any]:
        self.to_attempt()
        self.verify(**kwargs)
        return {"attempt_ref": self.attempt_ref, "report_ref": self.report_ref}

    def select(self, *, purpose: str = "delivery") -> ObjectRef:
        selection = self.svc.select_attempt(ctx("sel1"), self.attempt_ref,
                                            [self.attempt_ref.to_dict()], purpose,
                                            "only attempt with a passing report")
        return selection.object_refs[0]

    def to_delivery_ready(self, **kwargs) -> dict[str, Any]:
        info = self.to_verifying(**kwargs)
        self.select()
        return info

    def _passing_checks(self, items: list[dict[str, Any]]) -> list[CheckResult]:
        checks = []
        for item in items:
            if item.get("evidence_type") == "human_review":
                continue
            checks.append(CheckResult(
                check_id=item["item_id"],
                recipe_ref=ObjectRef.from_dict(item["recipe_ref"]),
                candidate_digest=CANDIDATE, result="pass", evidence_mode="test"))
        return checks

    def report(self) -> dict[str, Any]:
        payload, _ = self.svc._head_payload("verification", self.report_ref.object_id)
        return payload

    def task_payload(self) -> dict[str, Any]:
        payload, _ = self.svc._head_payload("task", self.task_ref.object_id)
        return payload

    def task_phase(self) -> str:
        return self.task_payload()["phase"]

    def operation(self, operation_id: str) -> dict[str, Any]:
        payload, _ = self.svc._head_payload("delivery", operation_id)
        return payload

    @staticmethod
    def operation_id_for(key: str) -> str:
        return "operation-"+sha256_digest({"principal":"human-1","apply":key})[:20]

    def applied(self, *, key: str = "ap1") -> tuple[Any, str, str]:
        """approve + apply; returns (operation_ref, snapshot_id, digest)."""
        approval_id, digest = self.approved()
        receipt = self.svc.apply_delivery(ctx(key), approval_id, "snap-1", digest)
        assert receipt.status == "accepted", receipt.error
        operation = oref("delivery", receipt.operation_id,
                         self.store.get_head("delivery", receipt.operation_id,
                                             "current")["revision_id"])
        return operation, "snap-1", digest

    # -- snapshot ----------------------------------------------------------
    def snapshot_body(self, *, candidate_digest: str = CANDIDATE,
                      verification_ref: ObjectRef | None = None,
                      task_ref: ObjectRef | None = None) -> dict[str, Any]:
        report = verification_ref or (
            oref("verification", self.report_ref.object_id, self.report_ref.revision_id))
        return {
            "schema_version": "1.0.0", "canonicalization": "rfc8785", "evidence_mode": "test",
            "project_id": PROJ,
            "task_ref": (task_ref or self.task_ref).to_dict(),
            "selected_attempt_ref": self.attempt_ref.to_dict(),
            "packet_ref": self.packet_ref.to_dict(),
            "requirement_refs": [self.prepared["requirement"].to_dict()],
            "design_refs": [self.prepared["design"].to_dict()],
            "acceptance_refs": [self.acceptance_ref.to_dict()],
            "rule_refs": [self.prepared["rules"].to_dict()],
            "scope_ref": self.scope_ref.to_dict(),
            "input_manifest_ref": self.input_ref.to_dict(),
            "context_manifest_ref": self.context_ref.to_dict(),
            "environment_ref": self.prepared["environment"].to_dict(),
            "verification_refs": [report.to_dict()],
            "candidate_digest": candidate_digest,
            "delivery": {"method": "bundle", "target_ref": self.target_ref.to_dict()},
            "artifacts": [self.artifact.to_dict()],
        }

    def freeze(self, *, snapshot_id: str = "snap-1", **kwargs) -> tuple[str, str, dict]:
        body = self.snapshot_body(**kwargs)
        receipt = self.svc.freeze_snapshot(ctx("f1"), snapshot_id, body)
        assert receipt.status == "committed", receipt.error
        return snapshot_id, sha256_digest(body), body

    def approved(self, *, approval_id: str = "appr-1", expires_at: str | None = None,
                 request_key: str = "req1", decide_key: str = "dec1") -> tuple[str, str]:
        snapshot_id, digest, _ = self.freeze()
        self.svc.request_approval(ctx(request_key), approval_id, snapshot_id, digest,
                                  expires_at=expires_at)
        decided = self.svc.decide_approval(ctx(decide_key), approval_id, "approved", digest,
                                           is_human=True, reason="looks good")
        assert decided.status == "committed", decided.error
        return approval_id, digest
