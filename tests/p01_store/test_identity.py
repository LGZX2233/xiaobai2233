"""Identity provisioning / binding / reconcile against real temp SQLite + files."""
from __future__ import annotations

import pytest

from project_kernel.contracts.errors import KernelError
from project_kernel.data.identity.registry import IdentityRegistry


def test_provision_creates_active_project_and_store(tmp_path):
    reg = IdentityRegistry(tmp_path / "data")
    try:
        receipt = reg.provision("user-1", "proj-a", "Project A",
                                str(tmp_path), "host-1")
        assert receipt["state"] == "active"
        assert reg.project_state("proj-a") == "active"
        store_file = tmp_path / "data" / "projects" / "proj-a" / "project.sqlite"
        assert store_file.exists()
        manifest = tmp_path / "data" / "projects" / "proj-a" / "project-manifest.json"
        assert manifest.exists()
    finally:
        reg.close()


def test_provision_same_id_different_root_rejected(tmp_path):
    reg = IdentityRegistry(tmp_path / "data")
    try:
        reg.provision("user-1", "proj-a", "Project A", str(tmp_path), "host-1")
        with pytest.raises(KernelError) as exc:
            reg.provision("user-1", "proj-a", "Project A",
                          str(tmp_path / "other"), "host-1")
        assert exc.value.error.code == "SCOPE_MISMATCH"
    finally:
        reg.close()


def test_binding_is_unique_per_canonical_key(tmp_path):
    reg = IdentityRegistry(tmp_path / "data")
    try:
        reg.provision("user-1", "proj-a", "A", str(tmp_path), "host-1")
        reg.provision("user-1", "proj-b", "B", str(tmp_path), "host-1")
        reg.bind("proj-a", "host-1", "workspace", "C:\\ws", "1")
        with pytest.raises(KernelError) as exc:
            reg.bind("proj-b", "host-1", "workspace", "C:\\ws", "1")
        assert exc.value.error.code == "SCOPE_MISMATCH"
        # version CAS
        with pytest.raises(KernelError) as exc2:
            reg.bind("proj-a", "host-1", "workspace", "C:\\ws", "2")
        assert exc2.value.error.code == "SCOPE_MISMATCH"
    finally:
        reg.close()


def test_reconcile_recovers_provisioning(tmp_path):
    from project_kernel.data.identity.registry import _schema_stamp

    reg = IdentityRegistry(tmp_path / "data")
    try:
        # Simulate a crash between the registry insert and the final activate:
        # directly register provisioning then reconcile.
        reg.conn.execute(
            "INSERT INTO identity_project (project_id, display_name, state, store_id,"
            " canonical_root, schema_stamp, created_at)"
            " VALUES ('proj-c','C','provisioning','store-c',?,?,?)",
            (str(tmp_path), _schema_stamp(), "2026-10-08T00:00:00Z"))
        reg.conn.execute(
            "INSERT INTO provision_receipt (provision_request_id, principal_id, project_id,"
            " state, store_id, manifest_ref, commit_seq, receipt_json)"
            " VALUES ('pr-c','user-1','proj-c','provisioning','store-c',NULL,1,'{}')")
        reg.conn.commit()
        # create the missing project store so reconcile can finish
        from project_kernel.data.store.store import Store
        proj_dir = tmp_path / "data" / "projects" / "proj-c"
        proj_dir.mkdir(parents=True, exist_ok=True)
        s = Store.open_project(proj_dir / "project.sqlite", "proj-c", "store-c")
        s.set_project_meta("proj-c", "store-c", "1.0.0", "2026-10-08T00:00:00Z")
        s.close()
        receipt = reg.reconcile("pr-c")
        assert receipt["state"] == "active"
        assert reg.project_state("proj-c") == "active"
    finally:
        reg.close()
