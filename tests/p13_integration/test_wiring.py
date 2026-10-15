"""The composition root really serves what it declares (P13 wiring).

Every declared machine command reaches a handler, human-only commands exist only
on the trusted human entry, and the implemented P06/P09 surfaces answer over the
real protocol.
"""
from __future__ import annotations

from pathlib import Path

from project_kernel.bootstrap import (
    HUMAN_ONLY_COMMANDS,
    MACHINE_COMMAND_ALLOWLIST,
    MACHINE_COMMANDS,
    QUERY_NAMES,
    InvocationContextRegistry,
    build_human_server,
    build_server,
)
from project_kernel.contracts import sha256_digest
from project_kernel.contracts.dto import CommandContext, ObjectRef, ResolvedScope
from project_kernel.corpus import CorpusService, DatasetPolicy, Sample, SplitSpec
from project_kernel.interfaces.rpc.framing import decode_frame, encode_frame
from project_kernel.interfaces.rpc.invocation import InteractionProof

from p01_store.helpers import make_store
from p13_integration.auth_helpers import build_test_server

PROJ = "proj-a"
POLICY_REF = {"project_id": PROJ, "object_type": "dataset_policy", "object_id": "ds",
              "revision_id": "rev-1"}
PURPOSE_REF = {"project_id": PROJ, "object_type": "dataset_purpose", "object_id": "eval-1",
               "revision_id": "rev-1"}


def _send(srv, obj):
    return decode_frame(srv.handle_line(encode_frame(obj)))


def _command(srv, rid, key, command, payload, context_id="ctx1"):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.command",
           "params": {"protocol_version": "1.0.0", "invocation_context_id": context_id,
                      "idempotency_key": key, "command": command,
                      "selector": {"project_id": PROJ}, "expected_heads": [],
                      "payload": payload}}
    return _send(srv, msg)


def _query(srv, rid, query, payload):
    msg = {"jsonrpc": "2.0", "id": rid, "method": "kernel.query",
           "params": {"protocol_version": "1.0.0", "invocation_context_id": "ctx1",
                      "selector": {"project_id": PROJ}, "query": query, "payload": payload}}
    return _send(srv, msg)


def _policy():
    return DatasetPolicy("ds", "evaluation")


def _server(store, **kwargs):
    return build_test_server(store, principal="user-1", mode="test",
                        dataset_policies={"rev-1": _policy()},
                        dataset_purposes={"rev-1": "evaluation"},
                        dataset_sink_root=kwargs.pop("dataset_sink_root", None), **kwargs)


def _register_sample(store, sample_id="s1"):
    """TEST-ONLY trusted writer: the kernel records candidates through its own port."""
    scope = ResolvedScope(project_id=PROJ, store_id="store-a", principal_id="user-1",
                          capabilities=frozenset({"project.admin"}), mode="test")
    ctx = CommandContext(scope=scope, command_id="cmd-sample", idempotency_key=f"sample-{sample_id}",
                         input_hash=sha256_digest({"sample": sample_id}))
    CorpusService(store, policies={"rev-1": _policy()},
                  purposes={"rev-1": "evaluation"}).record_sample(
        ctx, Sample(sample_id=sample_id, kind="success", group_id=f"{PROJ}:t1",
                    source_refs=(ObjectRef(PROJ, "attempt", "attempt-1", "rev-1"),),
                    input="q", output="a", source_digests=("a" * 64,),
                    redaction_receipt="redact-1"))


def test_declared_machine_commands_reject_empty_payloads(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    srv = _server(store)
    try:
        declared = srv.initialize_result()["supported_commands"]
        assert declared == sorted(MACHINE_COMMANDS)
        assert set(declared) <= MACHINE_COMMAND_ALLOWLIST
        assert not set(declared) & HUMAN_ONLY_COMMANDS

        for index, command in enumerate(MACHINE_COMMANDS):
            response = _command(srv, str(index), f"k-{index}", command, {})
            code = response.get("error", {}).get("data", {}).get("code")
            # an empty payload is a schema verdict, never "no handler registered"
            assert code == "INVALID_INPUT", (command, response)
    finally:
        store.close()


def test_human_only_commands_exist_only_on_the_human_entry(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    machine = _server(store)
    human = build_test_server(store, human=True, principal="human-1", mode="test")
    try:
        for index, command in enumerate(sorted(HUMAN_ONLY_COMMANDS)):
            refused = _command(machine, str(index), f"m-{index}", command,
                               {"approval_id": "a", "decision": "approved",
                                "snapshot_digest": "a" * 64, "reason": "r"})
            assert refused["error"]["data"]["code"] == "UNSUPPORTED_COMMAND", command

            served = _command(human, str(index), f"h-{index}", command,
                              {"approval_id": "missing", "decision": "approved",
                               "snapshot_digest": "a" * 64, "reason": "r"})
            code = served.get("error", {}).get("data", {}).get("code")
            assert code is not None and code != "UNSUPPORTED_COMMAND", (command, served)

        declared = human.initialize_result()["supported_commands"]
        assert declared == sorted(HUMAN_ONLY_COMMANDS)
        assert not set(declared) & set(MACHINE_COMMANDS)
    finally:
        store.close()


def test_human_decision_records_and_authorizes_the_export_chain(tmp_path):
    """Human review + human decision on the human entry, export on the machine entry."""
    store = make_store(tmp_path, project_id=PROJ)
    sink_root = tmp_path / "sink"
    machine = _server(store, dataset_sink_root=sink_root)
    human = build_test_server(store, human=True, principal="human-1", mode="test",
                               dataset_policies={"rev-1": _policy()},
                               dataset_purposes={"rev-1": "evaluation"})
    try:
        _register_sample(store, "s1")
        built = _command(machine, "1", "build-1", "dataset.build",
                         {"policy_ref": POLICY_REF,
                          "source_as_of": str(store.next_commit_seq() - 1),
                          "purpose_ref": PURPOSE_REF, "split_spec": SplitSpec().to_dict()})
        assert built["result"]["receipt"]["status"] == "accepted"
        candidate = ObjectRef(PROJ, "dataset_manifest", "ds",
                              store.get_head("dataset_manifest", "ds", "candidate")["revision_id"])

        reviewed = _command(human, "2", "review-1", "dataset.review",
                            {"dataset_ref": candidate.to_dict(),
                             "sample_reviews": [{"sample_id": "s1", "verdict": "accepted",
                                                 "reason": "verified by hand"}],
                             "reason": "sample review"})
        assert reviewed["result"]["receipt"]["status"] == "accepted", reviewed
        reviewed_ref = ObjectRef(PROJ, "dataset_review", "ds",
                                 store.get_head("dataset_review", "ds", "reviewed")["revision_id"])
        reviewed_digest = store.get_revision(reviewed_ref)["digest"]

        # the target description must be an immutable in-project revision
        target_ref = ObjectRef(PROJ, "delivery_target", "sink-1", "rev-1")
        seed_target = _decision_target(store, target_ref)

        bad_action = _command(human, "3", "dec-1", "decision.record",
                              {"subject_kind": "knowledge_promotion",
                               "subject_ref": reviewed_ref.to_dict(),
                               "subject_digest": reviewed_digest, "action": "dataset.export",
                               "target_scope": "approved_export_sink",
                               "target_ref": seed_target.to_dict(), "decision": "approved",
                               "reason": "wrong subject kind"})
        assert bad_action["result"]["receipt"]["status"] == "rejected"
        assert bad_action["result"]["receipt"]["error"]["code"] == "INVALID_INPUT"

        wrong_digest = _command(human, "4", "dec-2", "decision.record",
                                {"subject_kind": "dataset_export",
                                 "subject_ref": reviewed_ref.to_dict(),
                                 "subject_digest": "0" * 64, "action": "dataset.export",
                                 "target_scope": "approved_export_sink",
                                 "target_ref": seed_target.to_dict(), "decision": "approved",
                                 "reason": "stale digest"})
        assert wrong_digest["result"]["receipt"]["status"] == "rejected"
        assert wrong_digest["result"]["receipt"]["error"]["code"] == "ARTIFACT_DIGEST_MISMATCH"

        recorded = _command(human, "5", "dec-3", "decision.record",
                            {"subject_kind": "dataset_export",
                             "subject_ref": reviewed_ref.to_dict(),
                             "subject_digest": reviewed_digest, "action": "dataset.export",
                             "target_scope": "approved_export_sink",
                             "target_ref": seed_target.to_dict(), "decision": "approved",
                             "reason": "approved export"})
        assert recorded["result"]["receipt"]["status"] in {"accepted", "committed"}, recorded
        decision_ref = recorded["result"]["receipt"]["object_refs"][0]

        wrong_sink=_command(machine,"5b","wrong-sink","dataset.export",
            {"reviewed_dataset_ref":reviewed_ref.to_dict(),"sink_id":"sink-2","human_decision_ref":decision_ref})
        assert wrong_sink["error"]["data"]["code"]=="PERMISSION_DENIED"
        assert not (sink_root/"sink-2").exists()
        exported = _command(machine, "6", "exp-1", "dataset.export",
                            {"reviewed_dataset_ref": reviewed_ref.to_dict(),
                             "sink_id": "sink-1", "human_decision_ref": decision_ref})
        assert exported["result"]["receipt"]["status"] == "accepted", exported
        files = sorted(p.name for p in (sink_root / "sink-1" / "ds").glob("*/*"))
        assert files == ["manifest.json", "samples.jsonl"]
        before={str(path):path.stat().st_mtime_ns for path in sink_root.rglob("*") if path.is_file()}
        replay=_command(machine,"7","exp-1","dataset.export",{"reviewed_dataset_ref":reviewed_ref.to_dict(),"sink_id":"sink-1","human_decision_ref":decision_ref})
        assert replay["result"]["receipt"]==exported["result"]["receipt"]
        assert before=={str(path):path.stat().st_mtime_ns for path in sink_root.rglob("*") if path.is_file()}
        conflict=_command(machine,"8","exp-1","dataset.export",{"reviewed_dataset_ref":reviewed_ref.to_dict(),"sink_id":"sink-2","human_decision_ref":decision_ref})
        assert conflict["error"]["data"]["code"]=="IDEMPOTENCY_CONFLICT"
        assert not (sink_root/"sink-2").exists()

    finally:
        store.close()


def _decision_target(store, ref):
    """TEST-ONLY trusted writer: an immutable target description revision."""
    from project_kernel.data.store.uow import UnitOfWork

    scope = ResolvedScope(project_id=PROJ, store_id="store-a", principal_id="user-1",
                          capabilities=frozenset({"project.admin"}), mode="test")
    ctx = CommandContext(scope=scope, command_id="cmd-target",
                         idempotency_key="target-1",
                         input_hash=sha256_digest({"target": ref.object_id}))
    result: dict[str, object] = {}

    def cb(h):
        revision = h.records.append_revision(
            ref.object_type, ref.object_id,
            {"sink_id": "sink-1", "target_scope": "approved_export_sink"},
            "p05.delivery_target.v1")
        h.records.publish_head(revision, "current")
        result["ref"] = revision

    UnitOfWork(store, ctx, "delivery.target").execute(cb)
    return result["ref"]


def test_human_entry_applies_the_identity_gate(tmp_path):
    """The human entry reaches the real approval handler; a machine handle cannot approve."""
    from p04_delivery.helpers import Harness, ctx as p04_ctx

    harness = Harness(tmp_path)
    try:
        harness.to_delivery_ready()
        snapshot_id, digest, _ = harness.freeze()
        harness.svc.request_approval(p04_ctx("req1"), "appr-1", snapshot_id, digest)

        registry = InvocationContextRegistry()
        human = build_human_server(harness.store, principal="human-1", mode="test", enable_corpus=True,
                                   contexts=registry)
        payload = {"approval_id": "appr-1", "decision": "approved",
                   "snapshot_digest": digest, "reason": "ok"}

        machine_handle = registry.mint("agent-1", frozenset({"approval.decide"}), project_id=PROJ)
        refused = _command(human, "1", "k1", "approval.decide", payload,
                           context_id=machine_handle)
        receipt = refused["result"]["receipt"]
        assert receipt["status"] == "rejected"
        assert receipt["error"]["code"] == "HUMAN_IDENTITY_UNAVAILABLE"

        human_handle = registry.mint_human(
            "human-1", frozenset({"approval.decide"}),
            project_id=PROJ, proof=InteractionProof(source="test-interaction", verified=True))
        served = _command(human, "2", "k2", "approval.decide", payload,
                          context_id=human_handle)
        assert served["result"]["receipt"]["status"] == "committed", served
    finally:
        harness.close()


def test_declared_queries_answer_on_a_real_empty_store(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    srv = _server(store)
    try:
        assert srv.initialize_result()["supported_queries"] == sorted(QUERY_NAMES)
        safe = {"project.overview": {}, "project.timeline": {},
                "requirements.coverage": {}, "approvals.queue": {},
                "events.read": {"after": {"commit_seq": "0", "event_index": 0}, "limit": 10},
                "dataset.preview": {"policy_ref": POLICY_REF, "purpose_ref": PURPOSE_REF}}
        for index, (query, payload) in enumerate(safe.items()):
            response = _query(srv, str(index), query, payload)
            assert "result" in response, (query, response)
            assert response["result"]["as_of_seq"]
    finally:
        store.close()


def test_freeze_refuses_a_missing_required_artifact(tmp_path):
    """AC26: a snapshot may not freeze while a required artifact is not ready."""
    from project_kernel.application.delivery.service import DeliveryService
    from project_kernel.evidence import ArtifactStorage
    from p04_delivery.helpers import Harness, ctx as p04_ctx

    harness = Harness(tmp_path)
    try:
        harness.to_delivery_ready()
        body = harness.snapshot_body()
        body["artifacts"] = [{"artifact_id": "missing-art", "sha256": "b" * 64,
                              "size_bytes": "1", "media_type": "text/plain", "required": True}]

        guarded = DeliveryService(harness.store,
                                  artifact_storage=ArtifactStorage(tmp_path / "artifacts-2"))
        refused = guarded.freeze_snapshot(p04_ctx("fz1"), "snap-x", body)
        assert refused.status == "rejected"
        assert refused.error.code in {"ARTIFACT_MISSING", "ARTIFACT_DIGEST_MISMATCH"}

        # the harness's own published artifact really is ready -> freezing proceeds
        ready = DeliveryService(harness.store, artifact_storage=harness.storage)
        frozen = ready.freeze_snapshot(p04_ctx("fz2"), "snap-y", harness.snapshot_body())
        assert frozen.status == "committed", frozen.error
    finally:
        harness.close()


def test_dataset_build_over_rpc_then_preview(tmp_path):
    store = make_store(tmp_path, project_id=PROJ)
    srv = _server(store, dataset_sink_root=tmp_path / "sink")
    try:
        _register_sample(store, "s1")
        watermark = str(store.next_commit_seq() - 1)
        built = _command(srv, "1", "build-1", "dataset.build",
                         {"policy_ref": POLICY_REF, "source_as_of": watermark,
                          "purpose_ref": PURPOSE_REF,
                          "split_spec": SplitSpec().to_dict()})
        assert built["result"]["receipt"]["status"] == "accepted", built

        preview = _query(srv, "2", "dataset.preview",
                         {"policy_ref": POLICY_REF, "purpose_ref": PURPOSE_REF})
        data = preview["result"]["data"]
        assert data["status"] == "candidate"
        assert [item["sample_id"] for item in data["candidates"]] == ["s1"]
        assert data["purpose"] == "evaluation"

        # a purpose that does not match the policy is refused, never silently re-used
        repurposed = _query(srv, "3", "dataset.preview",
                            {"policy_ref": POLICY_REF,
                             "purpose_ref": {**PURPOSE_REF, "object_id": "train-1",
                                             "revision_id": "rev-9"}})
        assert repurposed["error"]["data"]["code"] == "REFERENCE_NOT_FOUND"
    finally:
        store.close()
