"""Trusted source results cannot cross persisted test/production execution modes."""
from dataclasses import replace
import json

import pytest

from project_kernel.application.attempt.service import AttemptService
from project_kernel.contracts import sha256_digest
from project_kernel.evidence import ArtifactStorage
from project_kernel.interfaces.rpc.ingest import SourceEvent, SourceIngestRequest, SourceStreamKey, ObservedRange
from project_kernel.interfaces.rpc.source_service import SourceIngestService
from p01_store.helpers import make_store
from p02_design.helpers import context, prepare_dispatch, seed
from p03_attempt.test_replay_regressions import CountingExecutor


def prepared_attempt(tmp_path, scenario):
    store = make_store(tmp_path)
    prepared = prepare_dispatch(store, tmp_path)
    storage = ArtifactStorage(tmp_path / "artifacts")
    service = AttemptService(store, CountingExecutor("unknown"), artifact_storage=storage,
        trusted_result_principals=("user-1",), trusted_provider_principals={"user-1": ("counting",)})
    payload = {"packet_ref": prepared["packet"].to_dict(), "strategy_id": "s1",
        "execution_root_ref": prepared["roots"]["s1"].to_dict()}
    started = service.attempt_start(context(store, "start", payload), payload)
    attempt, _ = service._head(started.operation_id)
    if scenario == "missing_attempt_mode":
        attempt = {key: value for key, value in attempt.items() if key != "mode"}
        seed(store, "attempt", started.operation_id, attempt)
    source = {"result_kind": "execution_result", "attempt_id": started.operation_id,
        "execution_handle_id": attempt["execution_handle_id"], "epoch": attempt["epoch"],
        "provider_id": attempt["provider_id"], "result": {"status": "completed", "evidence_mode": "test"}}
    scope = context(store, "scope").scope
    if scenario == "cross_scope":
        scope = replace(scope, mode="production")
        source["result"]["evidence_mode"] = "production"
    elif scenario == "cross_result":
        source["result"]["evidence_mode"] = "production"
    elif scenario == "missing_result_mode":
        source["result"].pop("evidence_mode")
    return store, storage, service, attempt, source, scope


@pytest.mark.parametrize("scenario", ["cross_scope", "cross_result", "missing_attempt_mode", "missing_result_mode"])
def test_settlement_refuses_cross_mode_or_missing_mode_without_changing_attempt(tmp_path, scenario):
    store, storage, service, attempt, source, scope = prepared_attempt(tmp_path, scenario)
    try:
        source_ref = seed(store, "source_result", "reviewed-result", source)
        payload = {"execution_handle_id": attempt["execution_handle_id"], "source_result_ref": source_ref.to_dict()}
        ctx = replace(context(store, "settle", payload), scope=scope)
        receipt = service.attempt_settle(ctx, payload)
        assert receipt.status == "rejected" and receipt.error.code == "INVALID_INPUT"
        assert service._head(attempt["attempt_id"])[0] == attempt
    finally:
        store.close()


@pytest.mark.parametrize("scenario", ["cross_scope", "cross_result", "missing_attempt_mode", "missing_result_mode"])
def test_ingest_refuses_cross_mode_or_missing_mode_and_rolls_back_source_cursor(tmp_path, scenario):
    store, storage, service, attempt, source, scope = prepared_attempt(tmp_path, scenario)
    try:
        artifact = storage.publish(storage.stage(json.dumps(source).encode(), "application/json"), "application/json")
        request = SourceIngestRequest(selector={"project_id": store.project_id}, idempotency_key="ingest",
            input_hash=sha256_digest(source), stream=SourceStreamKey("review-host", "session", "1"),
            events=(SourceEvent("1", sha256_digest(source), "1.0.0", artifact.to_dict(), scope.mode),),
            observed_range=ObservedRange(1, 1, False), principal_id="user-1")
        ingest = SourceIngestService(store, scope_resolver=lambda _: scope,
            bindings={"user-1": [("review-host", "session", "1")]}, artifact_storage=storage,
            trusted_provider_principals={"user-1": ("counting",)})
        receipt = ingest(request)
        assert receipt.status == "rejected" and receipt.error.code == "INVALID_INPUT"
        assert not store.conn.execute("SELECT 1 FROM source_event WHERE host_id='review-host'").fetchone()
        assert not store.conn.execute("SELECT 1 FROM source_cursor WHERE source_stream_key='review-host:session:1'").fetchone()
        assert service._head(attempt["attempt_id"])[0] == attempt
    finally:
        store.close()
