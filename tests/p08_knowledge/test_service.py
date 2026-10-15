"""KnowledgeService persistence/idempotency/promotion tests against a real
temporary SQLite store (no DDL changes; uses the P01 generic revision ledger)."""
from __future__ import annotations

import pytest

from project_kernel.contracts.dto import ObjectRef, ResolvedScope
from project_kernel.contracts.errors import KernelError
from project_kernel.knowledge import (
    ContextRequest,
    FeedbackConsumer,
    KnowledgeRevision,
    KnowledgeService,
    SourceMaterial,
)
from project_kernel.data.store.uow import UnitOfWork

from p01_store.helpers import make_context, make_store


def _scope(*extra_caps: str) -> ResolvedScope:
    caps = {"project.read"}
    caps.update(extra_caps)
    return ResolvedScope(project_id="proj-a", store_id="store-a",
                         principal_id="user-1", capabilities=frozenset(caps),
                         mode="test")


def _revision(title: str = "t", claim: str = "c") -> KnowledgeRevision:
    return KnowledgeRevision(title=title, claim=claim)


def _recorded(store, object_id: str = "r1", payload=None) -> dict:
    from project_kernel.contracts import sha256_digest
    payload = payload or {"title": "requirement", "goal": "g"}
    UnitOfWork(store, make_context(key=f"req-{object_id}"), "test.command").execute(
        lambda h: h.records.append_revision("requirement", object_id, payload,
                                            "requirement.v1"))
    return store.get_revision(ObjectRef("proj-a", "requirement", object_id, "rev-1"))


def _context_request(**kw) -> ContextRequest:
    base = dict(project_id="proj-a", task_id="task-1", attempt_id="att-1",
                purpose="dispatch", model_context_limit=1000, output_reserve=200,
                token_budget=500, mandatory_refs=("requirements.current",))
    base.update(kw)
    return ContextRequest(**base)


# --- knowledge revisions ------------------------------------------------------

def test_record_and_read_knowledge(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        ref = svc.record_knowledge(_scope(), _revision())
        row = svc.read_knowledge(ref.object_id)
        assert row["payload"]["title"] == "t"
        assert row["digest"]
    finally:
        store.close()


def test_revise_knowledge_is_versioned(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        ref = svc.record_knowledge(_scope(), _revision(title="v1"))
        ref2 = svc.revise_knowledge(_scope(), ref, _revision(title="v2", claim="c2"))
        assert ref2.revision_id != ref.revision_id
        assert svc.read_knowledge(ref.object_id)["payload"]["title"] == "v2"
    finally:
        store.close()


# --- feedback idempotency & scoring -------------------------------------------

def test_use_outcome_dedup_and_scoring(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        kref = svc.record_knowledge(_scope(), _revision())

        r1 = svc.record_use(_scope(), kref, "use-1", "adopted")
        assert r1.duplicate is False
        assert r1.new_score == 1.0

        r2 = svc.record_use(_scope(), kref, "use-1", "adopted")
        assert r2.duplicate is True
        assert r2.new_score == 1.0  # same use never scored twice

        r3 = svc.record_outcome(_scope(), "out-1", "success", use_source_key="use-1")
        assert r3.new_score == 2.0

        r4 = svc.record_outcome(_scope(), "out-1", "success", use_source_key="use-1")
        assert r4.duplicate is True
        assert r4.new_score == 2.0  # same outcome never scored twice
    finally:
        store.close()


def test_record_use_requires_existing_knowledge(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        ghost = ObjectRef("proj-a", "knowledge", "k-ghost", "rev-1")
        with pytest.raises(KernelError) as exc:
            svc.record_use(_scope(), ghost, "use-1", "adopted")
        assert exc.value.error.code == "REFERENCE_NOT_FOUND"
    finally:
        store.close()


def test_cross_project_scope_is_rejected(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        foreign = ResolvedScope(project_id="proj-b", store_id="store-a",
                                principal_id="user-1",
                                capabilities=frozenset({"project.read"}), mode="test")
        with pytest.raises(KernelError) as exc:
            svc.record_knowledge(foreign, _revision())
        assert exc.value.error.code == "SCOPE_MISMATCH"
    finally:
        store.close()


# --- promotion ----------------------------------------------------------------

class _SharedSink:
    def __init__(self, digest_override: str | None = None):
        self.writes: list[tuple[str, dict]] = []
        self.digest_override = digest_override

    def write(self, digest: str, payload: dict) -> dict:
        self.writes.append((digest, payload))
        return {"store_id": "shared-store", "object_id": "sk-1",
                "revision_id": "rev-1", "digest": self.digest_override or digest}


def test_promote_requires_knowledge_share(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        kref = svc.record_knowledge(_scope(), _revision())
        decision = ObjectRef("proj-a", "decision", "d-1", "rev-1")
        with pytest.raises(KernelError) as exc:
            svc.promote(_scope(), kref, "shared", decision, shared_sink=_SharedSink())
        assert exc.value.error.code == "PERMISSION_DENIED"
    finally:
        store.close()


def test_promote_verifies_shared_copy_digest(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        kref = svc.record_knowledge(_scope(), _revision())
        decision = ObjectRef("proj-a", "decision", "d-1", "rev-1")
        ok = svc.promote(_scope("knowledge.share"), kref, "shared", decision,
                         shared_sink=_SharedSink())
        assert ok.state == "completed"
        assert ok.shared_ref["digest"] == store.get_revision(kref)["digest"]

        # a second, distinct decision whose shared copy fails digest verification
        decision2 = ObjectRef("proj-a", "decision", "d-2", "rev-1")
        bad = svc.promote(_scope("knowledge.share"), kref, "shared", decision2,
                          shared_sink=_SharedSink(digest_override="f" * 64))
        assert bad.state == "failed"
    finally:
        store.close()


# --- resolve against the store (revision validity) -----------------------------

def test_verify_manifest_rejects_tampered_digest(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        row = _recorded(store)
        material = SourceMaterial(
            key="requirements.current", project_id="proj-a",
            source_ref=ObjectRef("proj-a", "requirement", "r1", "rev-1"),
            source_kind="requirement", token_count=10, token_mode="exact",
            content_digest="b" * 64)
        with pytest.raises(KernelError) as exc:
            svc.resolve_context(_context_request(), [material])
        assert exc.value.error.code == "ARTIFACT_DIGEST_MISMATCH"
    finally:
        store.close()


def test_verify_manifest_rejects_missing_revision(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        material = SourceMaterial(
            key="requirements.current", project_id="proj-a",
            source_ref=ObjectRef("proj-a", "requirement", "r1", "rev-99"),
            source_kind="requirement", token_count=10, token_mode="exact",
            content_digest="a" * 64)
        with pytest.raises(KernelError) as exc:
            svc.resolve_context(_context_request(), [material])
        assert exc.value.error.code == "REFERENCE_NOT_FOUND"
    finally:
        store.close()


def test_verify_manifest_accepts_valid_revision(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        row = _recorded(store)
        material = SourceMaterial(
            key="requirements.current", project_id="proj-a",
            source_ref=ObjectRef("proj-a", "requirement", "r1", "rev-1"),
            source_kind="requirement", token_count=10, token_mode="exact",
            content_digest=row["digest"])
        manifest = svc.resolve_context(_context_request(), [material])
        assert len(manifest.selections) == 1
    finally:
        store.close()


# --- consumer disable/enable & idempotent catch-up ------------------------------

def test_consumer_disable_preserves_records_and_catches_up(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        kref = svc.record_knowledge(_scope(), _revision())
        svc.record_use(_scope(), kref, "use-1", "adopted")
        svc.record_outcome(_scope(), "out-1", "success", use_source_key="use-1")

        consumer = FeedbackConsumer(svc, "score-consumer")
        applied = consumer.consume()
        assert len(applied) == 2
        assert consumer.score_record.score == 2.0

        # disabling stops consumption but never deletes the records
        consumer.disable()
        svc.record_use(_scope(), kref, "use-2", "adopted")
        assert consumer.consume() == []
        assert consumer.score_record.score == 2.0

        # re-enabling catches up idempotently
        consumer.enable()
        applied2 = consumer.consume()
        assert [a["key"] for a in applied2] == ["use-2"]
        assert consumer.score_record.score == 3.0

        # records were never lost
        assert len(svc._list_events("knowledge_use")) == 2
        assert len(svc._list_events("knowledge_outcome")) == 1
    finally:
        store.close()


def test_consumer_restart_replays_idempotently(tmp_path):
    store = make_store(tmp_path)
    try:
        svc = KnowledgeService(store)
        kref = svc.record_knowledge(_scope(), _revision())
        svc.record_use(_scope(), kref, "use-1", "adopted")
        svc.record_outcome(_scope(), "out-1", "success", use_source_key="use-1")
        svc.record_use(_scope(), kref, "use-2", "adopted")

        c1 = FeedbackConsumer(svc, "score-consumer")
        c1.consume()
        s1 = c1.score_record.score

        # a fresh consumer (restart) rebuilds the same score, no double count
        c2 = FeedbackConsumer(svc, "score-consumer")
        c2.consume()
        assert c2.score_record.score == s1 == 3.0
        assert c2.score_record.causal_refs == ("use-1", "use-2", "out-1")
    finally:
        store.close()
