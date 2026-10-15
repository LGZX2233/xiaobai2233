"""Read-only queries: receipt, events cursor, operation status, overview, coverage."""
from __future__ import annotations

import json

from project_kernel.application.design.service import DesignService
from project_kernel.application.delivery.service import DeliveryService
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import CommandContext, Cursor, ResolvedScope
from project_kernel.data.queries.service import QueryService

from p01_store.helpers import make_store

PROJ = "proj-a"


def _scope():
    return ResolvedScope(project_id=PROJ, store_id="store-a", principal_id="user-1",
                         capabilities=frozenset({"design.write", "dispatch.confirm"}),
                         mode="test")


def _ctx(key):
    return CommandContext(scope=_scope(), command_id="cmd", idempotency_key=key,
                          input_hash=sha256_digest({"key": key}))


def test_command_receipt_and_events_cursor(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    svc = DesignService(store)
    try:
        svc.create_task(_ctx("k1"), {"title": "t", "goal": "g",
                                     "requirement_refs": [], "mode": "test"})
        receipt = q.command_receipt("user-1", "k1")
        assert receipt is not None
        assert receipt["receipt"]["command"] == "task.create"
        # other principal cannot see this principal's receipt
        assert q.command_receipt("someone-else", "k1") is None

        events = q.events_read(Cursor(commit_seq="0", event_index=0))
        assert len(events) >= 1
        assert all(e["command_id"] == receipt["receipt"]["command_id"] for e in events
                   if e["event_type"] != "command.rejected")
    finally:
        store.close()


def test_operation_status_unknown_raises(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        from project_kernel.contracts.errors import KernelError
        try:
            q.operation_status("op-none")
            raise AssertionError("expected REFERENCE_NOT_FOUND")
        except KernelError as exc:
            assert exc.error.code == "REFERENCE_NOT_FOUND"
    finally:
        store.close()


def test_requirements_coverage_zero_linked_in_denominator(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    svc = DesignService(store)
    from p02_design.helpers import seed
    seed(store,"recipe","rec1",{"kind":"test"})
    try:
        saved = svc.requirement_save(_ctx("s1"), {"object_id": "req-a", "title": "t",
                                                  "source_text": "src", "assumptions": [],
                                                  "negative_requirements": [],
                                                  "source_refs": []})
        svc.requirement_confirm(_ctx("c1"), {
            "draft_ref": saved.object_refs[0].to_dict(),
            "acceptance_items": [{"item_id": "i1",
                                  "requirement_ref": {"project_id": PROJ,
                                                      "object_type": "requirement",
                                                      "object_id": "req-a",
                                                      "revision_id": "rev-1"},
                                  "recipe_ref": {"project_id": PROJ, "object_type": "recipe",
                                                 "object_id": "rec1", "revision_id": "rev-1"},
                                  "required": True, "evidence_type": "automated_test",
                                  "criterion": "c"}],
            "confirmed_assumptions": []})
        cov = q.requirements_coverage()
        # zero-linked requirement still shows in denominator, not skipped
        assert cov["denominator"] == 1
        assert cov["covered"] == 0
        assert cov["uncovered"] == ["req-a"]
    finally:
        store.close()

def test_list_revisions_timeline_approvals_archive(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    svc = DesignService(store)
    try:
        svc.create_task(_ctx("k1"), {"title": "t", "goal": "g",
                                     "requirement_refs": [], "mode": "test"})
        revs = q.list_revisions("task", after_seq=0)
        assert len(revs) >= 1
        assert revs[0]["payload"]["title"] == "t"
        tl = q.project_timeline()
        assert len(tl["events"]) >= 1
        assert q.approvals_queue()["queue"] == []
        assert q.archive_status()["deliveries"] == []
    finally:
        store.close()
