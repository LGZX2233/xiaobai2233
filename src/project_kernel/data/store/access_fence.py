"""Cross-process access fence using SQLite shared/exclusive transaction locks.

Writable Store connections hold a shared lease for their entire lifetime.
Maintenance holds an exclusive lease before opening or replacing the project DB.
The coordinator uses rollback journaling; WAL would not fence shared readers.
"""
from pathlib import Path
import sqlite3
from ...contracts.errors import KernelError, temporary_unavailable


class ProjectAccessFence:
    def __init__(self, path: Path, *, exclusive: bool = False):
        self.conn = None
        path = Path(path).resolve()
        coordinator = path.with_name(path.name + ".access.sqlite")
        conn = sqlite3.connect(str(coordinator), isolation_level=None, timeout=0)
        try:
            if conn.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise RuntimeError("project access coordinator requires DELETE journaling")
            conn.execute("CREATE TABLE IF NOT EXISTS access_guard (singleton INTEGER PRIMARY KEY)")
            conn.execute("BEGIN EXCLUSIVE" if exclusive else "BEGIN")
            conn.execute("SELECT * FROM access_guard").fetchall()
        except sqlite3.OperationalError as exc:
            conn.close()
            raise KernelError(temporary_unavailable("project writer or maintenance fence is active")) from exc
        except BaseException:
            conn.close()
            raise
        self.conn = conn

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
