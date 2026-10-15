"""P06 typed read APIs: project scoping and as_of-truncated latest revisions."""
from __future__ import annotations

from project_kernel.data.queries.service import QueryService

from p01_store.helpers import make_store
from p06_queries.helpers import PROJ, add_task, append_revision

OTHER_PROJECT = "proj-b"


def _insert_foreign_project_rows(store) -> None:
    """Write another project's rows into the same DB (shared store file case)."""
    store.conn.execute(
        "INSERT INTO entity (project_id, type, object_id, created_seq) VALUES (?,?,?,?)",
        (OTHER_PROJECT, "task", "task-foreign", 0))
    store.conn.execute(
        "INSERT INTO revision (project_id, type, object_id, revision_id, ordinal, parent_ref,"
        " payload_schema, payload_json, digest, commit_seq, command_id, principal_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (OTHER_PROJECT, "task", "task-foreign", "rev-1", 1, None, "task.v1",
         '{"task_id":"task-foreign"}', "c" * 64, 0, "cmd-foreign", "user-1"))


def test_list_revisions_is_project_scoped(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        add_task(store, "k1", "task-1")
        _insert_foreign_project_rows(store)

        revisions = q.list_revisions("task")
        assert [r["object_id"] for r in revisions] == ["task-1"], \
            "another project's revision must not leak into this project's read"
        assert all("foreign" not in r["object_id"] for r in revisions)

        latest = q.latest_revisions("task")
        assert [r["object_id"] for r in latest] == ["task-1"]
    finally:
        store.close()


def test_latest_revisions_truncates_at_as_of_and_keeps_one_per_object(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    q = QueryService(store)
    try:
        append_revision(store, "k1", "task", "task-1", {"task_id": "task-1", "phase": "draft"})
        as_of_rev1 = q.project_overview()["as_of_seq"]

        # second object, plus a newer revision of the first object
        append_revision(store, "k2", "task", "task-2", {"task_id": "task-2", "phase": "draft"})
        append_revision(store, "k3", "task", "task-1", {"task_id": "task-1",
                                                        "phase": "dispatch_ready"})

        live = q.latest_revisions("task")
        assert [r["object_id"] for r in live] == ["task-1", "task-2"]
        assert live[0]["revision_id"] == "rev-2"
        assert live[0]["ordinal"] == 2
        assert live[0]["payload"]["phase"] == "dispatch_ready"

        # truncated at the first revision's watermark: only rev-1 is visible
        at_rev1 = q.latest_revisions("task", as_of_seq=as_of_rev1)
        assert [r["object_id"] for r in at_rev1] == ["task-1"]
        assert at_rev1[0]["revision_id"] == "rev-1"
        assert at_rev1[0]["payload"]["phase"] == "draft"
        assert at_rev1[0]["as_of_seq"] == str(as_of_rev1)

        # list_revisions also honours the as_of bound
        bounded = q.list_revisions("task", as_of_seq=as_of_rev1)
        assert [(r["object_id"], r["revision_id"]) for r in bounded] == [("task-1", "rev-1")]
    finally:
        store.close()


def test_queries_run_on_a_read_only_store_connection(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    try:
        add_task(store, "k1", "task-1")
        commits = store.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0]
    finally:
        store.close()

    read_only = make_store(tmp_path, project_id=PROJ, read_only=True)
    try:
        q = QueryService(read_only)
        assert q.project_overview()["data"]["object_counts"]["task"] == 1
        assert q.project_timeline()["events"]
        assert q.latest_revisions("task")[0]["revision_id"] == "rev-1"
        assert q.requirements_coverage()["denominator"] == 0
        rebuild = q.rebuild_read_model()
        assert rebuild["data"]["consistent"] is True
        assert rebuild["data"]["persisted"] is False
        assert read_only.conn.execute("SELECT COUNT(*) FROM commit_log").fetchone()[0] == commits
    finally:
        read_only.close()
