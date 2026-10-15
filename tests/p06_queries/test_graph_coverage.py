"""P06 trace / coverage tests: typed multi-hop graph and the N/A denominator."""
from __future__ import annotations

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.data.queries.service import QueryService

from p01_store.helpers import make_store
from p06_queries.helpers import PROJ, add_task, append_revision, ref


def test_trace_multihop_and_same_name_different_type(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        # requirement "shared" (type=requirement) pointing at a source doc
        requirement = append_revision(store, "r1", "requirement", "shared",
                                      {"title": "shared",
                                       "source_refs": [ref("source_doc", "doc-1", "rev-9")]})
        task = add_task(store, "t1", "task-1")
        packet = append_revision(store, "d1", "execution_packet", "packet-1", {
            "task_ref": task.to_dict(),
            "strategies": [{"strategy_id": "s1"}],
            "requirement_refs": [requirement.to_dict()],
            # same object_id, different object_type -> must stay a distinct node
            "rule_refs": [ref("rules", "shared", "rev-1")],
            "acceptance_refs": [ref("acceptance", "acc-1")],
            "scope": {}, "mode": "test"})

        walked = q.project_trace(packet.to_dict(), direction="outgoing", max_depth=2)
        assert walked["completeness"] == "complete"
        assert walked["data"]["truncated"] is False
        nodes = walked["data"]["nodes"]
        types_by_id: dict[str, set[str]] = {}
        for node in nodes:
            types_by_id.setdefault(node["object_id"], set()).add(node["object_type"])
        assert types_by_id["shared"] == {"requirement", "rules"}
        by_type = {n["object_type"]: n for n in nodes}
        assert by_type["requirement"]["depth"] == 1
        assert by_type["source_doc"]["depth"] == 2
        relations = {e["relation"] for e in walked["data"]["edges"]}
        assert "requirement_refs" in relations
        assert "source_refs" in relations

        incoming = q.project_trace(requirement.to_dict(), direction="incoming", max_depth=1)
        assert any(n["object_id"] == packet.object_id for n in incoming["data"]["nodes"])

        # depth cut-off is explicit, never silently partial
        cut = q.project_trace(packet.to_dict(), direction="outgoing", max_depth=1)
        assert cut["data"]["truncated"] is True
        assert cut["completeness"] == "incomplete"

        with pytest.raises(KernelError) as exc:
            q.project_trace(ref("task", "no-such-task", "rev-1"), direction="both", max_depth=1)
        assert exc.value.error.code == "REFERENCE_NOT_FOUND"
    finally:
        store.close()


def test_coverage_counts_linked_and_marks_zero_link_not_applicable(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        linked = append_revision(store, "r1", "requirement", "req-linked",
                                 {"title": "req-linked", "source_refs": []})
        append_revision(store, "r2", "requirement", "req-orphan",
                        {"title": "req-orphan", "source_refs": []})
        task = add_task(store, "t1", "task-1")
        append_revision(store, "d1", "execution_packet", "packet-1", {
            "task_ref": task.to_dict(), "strategies": [{"strategy_id": "s1"}],
            "requirement_refs": [linked.to_dict()],
            "acceptance_refs": [ref("acceptance", "acc-1")], "rule_refs": [],
            "scope": {}, "mode": "test"})

        cov = q.requirements_coverage()
        assert cov["denominator"] == 2
        assert cov["covered"] == 1
        assert cov["uncovered"] == ["req-orphan"]
        assert cov["not_applicable"] == 1
        assert cov["not_applicable_ids"] == ["req-orphan"]
        statuses = {r["object_id"]: r["coverage"] for r in cov["requirements"]}
        assert statuses == {"req-linked": "covered", "req-orphan": "not_applicable"}
        orphan = next(r for r in cov["requirements"] if r["object_id"] == "req-orphan")
        assert orphan["not_applicable"] is True
        assert orphan["link_count"] == 0

        scoped = q.requirements_coverage([linked.to_dict()])
        assert scoped["denominator"] == 1
        assert scoped["covered"] == 1
    finally:
        store.close()
