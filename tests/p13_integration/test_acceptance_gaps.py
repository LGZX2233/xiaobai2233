"""Regression evidence for exact freeze references and public RPC pagination."""
from __future__ import annotations

from project_kernel.data.store.uow import UnitOfWork
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from p01_store.helpers import make_store
from p02_design.helpers import context, seed
from p04_delivery.helpers import Harness, ctx as delivery_ctx
from p13_integration.auth_helpers import build_test_server


def test_freeze_rejects_nonexistent_pinned_task_revision_then_accepts_valid_body(tmp_path):
    harness = Harness(tmp_path)
    try:
        harness.to_delivery_ready()
        invalid = harness.snapshot_body()
        invalid["task_ref"]["revision_id"] = "rev-never-existed"

        rejected = harness.svc.freeze_snapshot(
            delivery_ctx("freeze-bad-task-revision"), "snap-invalid-task-revision", invalid)
        assert rejected.status == "rejected"
        assert rejected.error.code == "REFERENCE_NOT_FOUND"
        assert harness.store.get_head(
            "delivery_snapshot", "snap-invalid-task-revision", "current") is None

        valid = harness.snapshot_body()
        accepted = harness.svc.freeze_snapshot(
            delivery_ctx("freeze-valid-task-revision"), "snap-valid-task-revision", valid)
        assert accepted.status == "committed", accepted.error
        assert harness.store.get_head(
            "delivery_snapshot", "snap-valid-task-revision", "current") is not None
    finally:
        harness.close()


def _seed_approvals(store, prefix: str, count: int) -> None:
    def write(handles):
        refs = []
        for index in range(count):
            approval_id = f"{prefix}-{index:03d}"
            ref = handles.records.append_revision("approval", approval_id,
                {"snapshot_id": f"snapshot-{index:03d}",
                 "snapshot_digest": "a" * 64, "status": "pending"}, "approval.v1")
            handles.records.publish_head(ref, "current", expected_head_version=None)
            refs.append(ref)
        handles.outcome.object_refs = tuple(refs)

    receipt = UnitOfWork(store, context(store, f"seed-{prefix}"), "system.ingest").execute(write)
    assert receipt.status == "committed", receipt.error


def _query_approvals(server, project_id: str, request_id: str, *, page_token: str | None = None):
    params = {"protocol_version": "1.0.0", "invocation_context_id": "ctx1",
              "selector": {"project_id": project_id}, "query": "approvals.queue", "payload": {}}
    if page_token is not None:
        params["page_token"] = page_token
    response = decode_frame(server.handle_line(encode_frame({
        "jsonrpc": "2.0", "id": request_id, "method": "kernel.query", "params": params})))
    return response


def test_rpc_approval_pages_keep_watermark_and_reject_foreign_project_token(tmp_path):
    root_a = tmp_path / "project-a"
    root_b = tmp_path / "project-b"
    root_a.mkdir()
    root_b.mkdir()
    store_a = make_store(root_a, project_id="proj-a", store_id="store-a")
    store_b = make_store(root_b, project_id="proj-b", store_id="store-b")
    try:
        _seed_approvals(store_a, "approval-a", 55)
        _seed_approvals(store_b, "approval-b", 55)
        server_a = build_test_server(store_a)
        server_b = build_test_server(store_b)

        first_response = _query_approvals(server_a, "proj-a", "page-a-1")
        assert "result" in first_response, first_response
        first = first_response["result"]
        assert len(first["data"]["queue"]) == 50
        assert first["next_page_token"]

        seed(store_a, "approval", "approval-a-000", {
            "snapshot_id": "snapshot-000", "snapshot_digest": "a" * 64,
            "status": "approved"})
        seed(store_a, "approval", "approval-a-future", {
            "snapshot_id": "snapshot-future", "snapshot_digest": "b" * 64,
            "status": "pending"})

        second_response = _query_approvals(server_a, "proj-a", "page-a-2",
                                           page_token=first["next_page_token"])
        assert "result" in second_response, second_response
        second = second_response["result"]
        assert second["as_of_seq"] == first["as_of_seq"]
        first_ids = {row["approval_id"] for row in first["data"]["queue"]}
        second_rows = second["data"]["queue"]
        second_ids = {row["approval_id"] for row in second_rows}
        all_ids = first_ids | second_ids
        assert len(first_ids) == 50
        assert len(second_ids) == 5
        assert len(all_ids) == 55
        assert first_ids.isdisjoint(second_ids)
        assert "approval-a-future" not in all_ids
        historical = next(row for row in second_rows if row["approval_id"] == "approval-a-000")
        assert historical["status"] == "pending"

        other_page = _query_approvals(server_b, "proj-b", "page-b-1")
        assert "result" in other_page, other_page
        foreign_token = other_page["result"]["next_page_token"]
        assert foreign_token
        refused = _query_approvals(server_a, "proj-a", "foreign-page-token",
                                   page_token=foreign_token)
        assert refused["error"]["data"]["code"] == "INVALID_INPUT"
    finally:
        store_a.close()
        store_b.close()
