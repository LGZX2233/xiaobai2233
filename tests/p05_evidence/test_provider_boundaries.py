"""Provider effects follow authorization and commit; reconciliation never replays."""
import ast
from dataclasses import replace
from pathlib import Path

import pytest

from project_kernel.data.queries.service import QueryService
from project_kernel.application.evidence_service import EvidenceService
from project_kernel.application.environment_service import EnvironmentService
from project_kernel.application.delivery.service import DeliveryService
from project_kernel.contracts.errors import KernelError
from project_kernel.evidence.provider import FileEvidenceProvider, IsolatedRestoreTarget
from p01_store.helpers import make_store
from p02_design.helpers import context, prepare_dispatch, seed
from p05_evidence.test_service import state


class RecordingEvidence:
    artifact_available = False
    sink_ids = frozenset()
    backup_available = True
    restore_target_info = {"target_id": "injected", "restore_mode": "isolated_copy"}

    def __init__(self, store, *, fail=False):
        self.store = store
        self.calls = []
        self.fail = fail

    def backup(self, operation_id):
        assert not self.store.conn.in_transaction
        assert self.store.get_head("evidence_operation", operation_id, "current")
        self.calls.append(("backup", operation_id))
        if self.fail:
            raise OSError("provider interrupted after the durable claim")
        return {"all_ok": True, "backup_path": "opaque-provider-locator", "file_sha256": "a" * 64}

    def restore(self, source, operation_id):
        assert not self.store.conn.in_transaction
        assert self.store.get_head("evidence_operation", operation_id, "current")
        self.calls.append(("restore", operation_id))
        return {"status": "succeeded", "restored_path": "opaque-offline-result"}


def backup_request(store):
    store_ref = seed(store, "store", "store-a", {"store_id": store.store_id})
    policy = seed(store, "policy", "backup", {})
    return {"store_ref": store_ref.to_dict(), "policy_ref": policy.to_dict()}


def approve_restore(store, service, backup_ref, *, wrong_target=False):
    receipt = service.restore_plan(context(store, "plan"), {
        "revision_or_backup_ref": backup_ref, "restore_kind": "disaster_recovery", "reason": "test"})
    plan_ref = receipt.object_refs[0]
    plan = store.get_revision(plan_ref)
    target = plan["payload"]["target_ref"]
    if wrong_target:
        target = seed(store, "restore_target", "different", {"target_id": "different"}).to_dict()
    decision = DeliveryService(store).decision_record(context(store, "approve"), {
        "subject_kind": "restore_plan", "subject_ref": plan_ref.to_dict(),
        "subject_digest": plan["digest"], "action": "restore.apply", "target_scope": "project",
        "target_ref": target, "decision": "approved", "reason": "test"}, is_human=True)
    return {"restore_plan_ref": plan_ref.to_dict(), "human_decision_ref": decision.object_refs[0].to_dict()}


@pytest.mark.parametrize("fail", [False, True])
def test_injected_backup_runs_after_commit_once_and_retains_failure(tmp_path, fail):
    store = make_store(tmp_path)
    try:
        provider = RecordingEvidence(store, fail=fail)
        service = EvidenceService(store, provider=provider)
        payload = backup_request(store)
        ctx = context(store, "backup", payload)
        receipt = service.backup_create(ctx, payload)
        operation = state(store, receipt)
        assert operation["status"] == ("unknown" if fail else "succeeded")
        if fail:
            assert operation["error"]["type"] == "OSError"
        assert service.backup_create(ctx, payload) == receipt
        assert provider.calls == [("backup", receipt.operation_id)]
    finally:
        store.close()


def test_rejected_backup_never_calls_provider(tmp_path):
    store = make_store(tmp_path)
    try:
        provider = RecordingEvidence(store)
        service = EvidenceService(store, provider=provider)
        payload = backup_request(store)
        ctx = context(store, "denied", payload)
        denied = replace(ctx, scope=replace(ctx.scope, capabilities=()))
        with pytest.raises(KernelError):
            service.backup_create(denied, payload)
        foreign_store = seed(store, "store", "wrong", {"store_id": "another-store"})
        invalid = {**payload, "store_ref": foreign_store.to_dict()}
        receipt = service.backup_create(context(store, "invalid", invalid), invalid)
        assert receipt.status == "rejected"
        assert provider.calls == []
    finally:
        store.close()


@pytest.mark.parametrize("wrong_target", [False, True])
def test_injected_restore_requires_matching_human_approval(tmp_path, wrong_target):
    store = make_store(tmp_path)
    try:
        provider = RecordingEvidence(store)
        service = EvidenceService(store, provider=provider)
        payload = backup_request(store)
        receipt = service.backup_create(context(store, "backup", payload), payload)
        payload = approve_restore(store, service, state(store, receipt)["result_refs"][0], wrong_target=wrong_target)
        provider.calls.clear()
        if wrong_target:
            with pytest.raises(KernelError):
                service.restore_apply(context(store, "restore", payload), payload)
            assert provider.calls == []
        else:
            receipt = service.restore_apply(context(store, "restore", payload), payload)
            assert state(store, receipt)["status"] == "succeeded"
            assert provider.calls == [("restore", receipt.operation_id)]
    finally:
        store.close()


@pytest.mark.parametrize("fail", [False, True])
def test_environment_provider_runs_once_after_commit_and_never_when_denied(tmp_path, fail):
    store = make_store(tmp_path)
    try:
        prepared = prepare_dispatch(store, tmp_path)
        recipe = seed(store, "recipe", "probe", {"dependencies": [{"name": "python"}]})
        calls = []

        class Probe:
            def probe(self, recipes):
                assert not store.conn.in_transaction
                calls.append(recipes)
                if fail:
                    raise OSError("runtime metadata unavailable")
                return {"status": "ready", "facts": [{"name": "python", "state": "satisfied"}]}

        service = EnvironmentService(store, Probe())
        payload = {"task_ref": prepared["task"].to_dict(), "execution_root_ref": prepared["roots"]["s1"].to_dict(),
            "requirement_refs": [prepared["requirement"].to_dict()], "recipe_refs": [recipe.to_dict()]}
        ctx = context(store, "probe", payload)
        with pytest.raises(KernelError):
            service.environment_probe(replace(ctx, scope=replace(ctx.scope, capabilities=())), payload)
        assert calls == []
        receipt = service.environment_probe(ctx, payload)
        assert state(store, receipt)["status"] == ("unknown" if fail else "ready")
        assert service.environment_probe(ctx, payload) == receipt
        assert calls == [[{"dependencies": [{"name": "python"}]}]]
    finally:
        store.close()


def test_backup_and_isolated_restore_reconcile_without_repeating_effects(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    try:
        provider = FileEvidenceProvider(store, backup_root=tmp_path / "backups",
            restore_target=IsolatedRestoreTarget(tmp_path / "restored", "isolated"))
        service = EvidenceService(store, provider=provider)
        payload = backup_request(store)
        settle = service._settle
        monkeypatch.setattr(service, "_settle", lambda *a, **k: None)
        backup = service.backup_create(context(store, "backup", payload), payload)
        monkeypatch.setattr(service, "_settle", settle)
        monkeypatch.setattr(provider, "backup", lambda *a: pytest.fail("backup effect replayed"))
        reconciled = service.reconcile(context(store, "reconcile-backup"), backup.operation_id)
        assert reconciled["status"] == "succeeded"
        payload = approve_restore(store, service, reconciled["result_refs"][0])
        original = seed(store, "requirement", "later", {"title": "preserved in live store"})
        monkeypatch.setattr(service, "_settle", lambda *a, **k: None)
        restored = service.restore_apply(context(store, "restore", payload), payload)
        destination = tmp_path / "restored" / (restored.operation_id + ".sqlite")
        assert destination.is_file()
        before = destination.stat().st_mtime_ns
        monkeypatch.setattr(service, "_settle", settle)
        monkeypatch.setattr(provider, "restore", lambda *a: pytest.fail("restore effect replayed"))
        reconciled = service.reconcile(context(store, "reconcile-restore"), restored.operation_id)
        assert reconciled["status"] == "succeeded" and reconciled["reconciled"]
        assert destination.stat().st_mtime_ns == before
        assert store.get_revision(original)
    finally:
        store.close()


def test_backup_reconciliation_rechecks_saved_bytes(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    try:
        provider = FileEvidenceProvider(store, backup_root=tmp_path / "backups")
        service = EvidenceService(store, provider=provider)
        payload = backup_request(store)
        monkeypatch.setattr(service, "_settle", lambda *a, **k: None)
        receipt = service.backup_create(context(store, "backup", payload), payload)
        image = next((tmp_path / "backups" / receipt.operation_id).glob("*.sqlite"))
        image.write_bytes(b"damaged saved copy")
        with pytest.raises(KernelError):
            service.reconcile(context(store, "reconcile"), receipt.operation_id)
        assert state(store, receipt)["status"] == "claimed"
    finally:
        store.close()


_APPLICATION_IMPORTS = {"os", "sys", "pathlib", "shutil", "sqlite3", "subprocess", "platform", "importlib", "packaging"}
_IO_CALLS = {"open", "read_text", "read_bytes", "write_text", "write_bytes", "mkdir", "unlink", "rename",
    "glob", "rglob", "resolve", "is_file", "is_dir", "exists", "stat", "fsync", "copyfileobj", "file_digest"}


def application_effect_violations(source):
    """Detect direct runtime/file effects in the three service modules."""
    failures = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            failures.extend(alias.name for alias in node.names if alias.name.split(".")[0] in _APPLICATION_IMPORTS)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in _APPLICATION_IMPORTS:
                failures.append(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _IO_CALLS:
                failures.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in _IO_CALLS or (node.func.attr == "execute" and
                        isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "conn"):
                    failures.append(node.func.attr)
    return failures


def test_application_modules_have_no_direct_filesystem_runtime_or_sql_effects():
    source_root = Path(__file__).resolve().parents[2] / "src" / "project_kernel"
    for name in ("evidence_service.py", "environment_service.py", "recovery_authorization.py"):
        path = source_root / "application" / name
        assert application_effect_violations(path.read_text(encoding="utf-8")) == [], name


@pytest.mark.parametrize("source", ["from pathlib import Path", "import platform", "value.read_text()", "open('f')", "store.conn.execute('SELECT 1')"])
def test_layer_check_rejects_direct_effects(source):
    assert application_effect_violations(source)


def test_evidence_and_internal_providers_never_import_application():
    source_root = Path(__file__).resolve().parents[2] / "src" / "project_kernel"
    for directory in ("evidence", "internal"):
        for path in (source_root / directory).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or "", *(alias.name for alias in node.names)]
                assert all("application" not in name.split(".") for name in imports), str(path)


def test_environment_provider_cannot_rebind_frozen_references(tmp_path):
    store = make_store(tmp_path)
    try:
        prepared = prepare_dispatch(store, tmp_path)
        recipe = seed(store, "recipe", "probe", {"dependencies": [{"name": "python"}]})
        observed = {"status": "ready", "facts": [{"name": "python", "state": "satisfied"}],
            "task_ref": {"object_id": "forged"}, "execution_root_ref": {"object_id": "forged-root"},
            "recipe_refs": [], "requirement_refs": [], "mode": "production", "operation_id": "forged-operation"}

        class Probe:
            def probe(self, recipes):
                return observed

        service = EnvironmentService(store, Probe())
        payload = {"task_ref": prepared["task"].to_dict(), "execution_root_ref": prepared["roots"]["s1"].to_dict(),
            "requirement_refs": [prepared["requirement"].to_dict()], "recipe_refs": [recipe.to_dict()]}
        receipt = service.environment_probe(context(store, "probe", payload), payload)
        result = state(store, receipt)
        for key, expected in payload.items():
            assert result[key] == expected
        assert result["mode"] == "test"
        assert result["provider_result"] == observed
        assert result.get("operation_id", receipt.operation_id) == receipt.operation_id
    finally:
        store.close()


def test_evidence_provider_cannot_replace_operation_identity_or_publish_foreign_type(tmp_path):
    store = make_store(tmp_path)
    try:
        provider = RecordingEvidence(store)
        service = EvidenceService(store, provider=provider)
        payload = backup_request(store)
        backup = service.backup_create(context(store, "backup", payload), payload)
        payload = approve_restore(store, service, state(store, backup)["result_refs"][0])
        observed = {"status": "succeeded", "operation_id": "forged-operation", "command": "artifact.register",
            "principal_id": "forged-principal", "epoch": "99", "payload": {}, "pinned": {},
            "result_refs": [{"object_id": "forged"}], "object_type": "task", "body": {"title": "forged"}}
        provider.restore = lambda source, operation_id: observed
        receipt = service.restore_apply(context(store, "restore", payload), payload)
        result = state(store, receipt)
        assert result["operation_id"] == receipt.operation_id
        assert result["command"] == "restore.apply"
        assert result["principal_id"] == "user-1" and result["epoch"] == "1"
        assert result["payload"] == payload and result["pinned"]["backup"]["all_ok"]
        assert result["result_refs"] == []
        assert store.get_head("task", receipt.operation_id, "current") is None
        assert result["provider_result"] == observed
    finally:
        store.close()


def test_archive_provider_cannot_credit_another_sink_and_retains_raw_receipt(tmp_path):
    from project_kernel.evidence import ArchiveManifest

    store = make_store(tmp_path)
    try:
        provider = RecordingEvidence(store)
        provider.sink_ids = frozenset({"good"})
        observed = {"state": "succeeded", "sink_id": "forged", "verified": True}
        provider.archive = lambda *args, **kwargs: observed
        service = EvidenceService(store, provider=provider)
        manifest = seed(store, "archive_manifest", "manifest",
            ArchiveManifest("manifest", "a" * 64, (), (), ("good",)).body())
        payload = {"manifest_ref": manifest.to_dict(), "sink_id": "good"}
        receipt = service.archive_export(context(store, "archive", payload), payload)
        result = state(store, receipt)
        assert result["status"] == "unknown"
        assert result["error"]["type"] == "ProviderReceiptMismatch"
        assert "sink_receipt" not in result
        assert result["provider_result"]["sink_receipt"] == observed
        assert result["payload"] == payload
    finally:
        store.close()


@pytest.mark.parametrize("overrides", [
    {"manifest_id": "different"}, {"digest": "b" * 64},
    {"verified": False}, {"verified": "true"}, {"state": "pending"},
])
def test_archive_receipt_must_match_pinned_manifest_and_verified_terminal_state(tmp_path, overrides):
    from project_kernel.evidence import ArchiveManifest

    store = make_store(tmp_path)
    try:
        provider = RecordingEvidence(store)
        provider.sink_ids = frozenset({"good"})
        manifest = ArchiveManifest("manifest", "a" * 64, (), (), ("good",))
        manifest_ref = seed(store, "archive_manifest", "manifest", manifest.body())
        seed(store, "archive_status", "task", {"manifest_ref": manifest_ref.to_dict(),
            "required_sinks": ["good"], "sink_states": {}, "source_flushed": True,
            "overall": "export_pending"})
        raw = {"manifest_id": manifest.manifest_id, "digest": manifest.digest(),
            "sink_id": "good", "state": "succeeded", "verified": True, **overrides}
        provider.archive = lambda *args, **kwargs: raw
        service = EvidenceService(store, provider=provider)
        payload = {"manifest_ref": manifest_ref.to_dict(), "sink_id": "good"}
        receipt = service.archive_export(context(store, "archive", payload), payload)
        operation = state(store, receipt)
        assert operation["status"] == "unknown"
        assert operation["provider_result"]["sink_receipt"] == raw
        assert "sink_receipt" not in operation
        status = QueryService(store).latest_revisions("archive_status")[0]["payload"]
        assert status["sink_states"] == {} and status["overall"] == "export_pending"
    finally:
        store.close()
