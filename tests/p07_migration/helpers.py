"""P07 test helpers: real temporary SQLite/files, no fake providers."""
from __future__ import annotations

from pathlib import Path

from project_kernel.data.store.store import Store
from project_kernel.migration.legacy import SyntheticLegacySample

PROJECT_MAPPING = {"p-a": "proj-a", "p-b": "proj-b"}


def make_legacy_source(tmp_path: Path) -> Path:
    src = tmp_path / "legacy"
    src.mkdir(exist_ok=True)
    SyntheticLegacySample().build_sqlite(src / "legacy.sqlite")
    return src


def make_store(tmp_path: Path, project_id: str = "proj-a",
               store_id: str = "store-a") -> Store:
    return Store.open_project(tmp_path / f"{project_id}.sqlite", project_id, store_id)


def count(table: str, store: Store, *, project_id: str = "proj-a") -> int:
    row = store.conn.execute(
        f'SELECT COUNT(*) FROM {table} WHERE project_id=?', (project_id,)).fetchone()
    return int(row[0])
