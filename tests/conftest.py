"""Root pytest configuration (owned by P00 until G0, then P13).

Adds src/ to sys.path so `project_kernel` imports work without an editable
install. Tests must always inject their own temporary SQLite/file roots via
tmp_path; no test may default to the current working directory or real user
data directories.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
TESTS = Path(__file__).resolve().parent
for p in (SRC, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
