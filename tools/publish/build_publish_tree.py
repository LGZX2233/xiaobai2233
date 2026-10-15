#!/usr/bin/env python3
"""Build the standalone public tree from an explicit allowlist (stdlib only, read-only on the source).

The working repository is never modified: everything not on the allowlist is simply not copied.
Outputs:
  --out DIR          the publish tree (recreated on every run; refuses to touch the source)
  --report-dir DIR   MANIFEST.md and report.json (default: parent of --out)
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

DEFAULT_SRC = str(Path(__file__).resolve().parents[2])  # tools/publish/ lives inside the working repository
DEFAULT_OUT = os.path.join(os.environ.get("PK_PUBLISH_WORK", "/tmp/publish"), "tree")

# ------------------------------------------------------------------ allowlist
ROOT_FILES = ["README.md", "README.en.md", "pyproject.toml", ".gitignore", ".gitattributes", "AGENTS.md"]
ROOT_DIRS = ["src", "contracts", "fixtures", "bridge", "tests", "adapters", "evidence", ".agents"]

# tools/ is file-level: only maintained tools, nothing that needs the excluded raw acceptance evidence.
TOOLS_FILES = ["README.md", "verify_g2_evidence.py", "capture_validation.py", "pk_human_approve.py"]
TOOLS_GLOBS = ["*.ps1"]
TOOLS_DIRS = ["publish", "agh-sandbox"]

DOCS_FILES = ["index.html", ".nojekyll"]
DOCS_DIRS = ["assets", "submission", "architecture", "modules", "records", "requirements", "frontend",
             "development", "plans", "changes"]
# G2 summaries only: reports and the four small metadata files of the final round; no raw evidence, failures or zips.
DOCS_ACCEPTANCE_FILES = ["G0-report.md", "G1-report.md", "G2-report.md", "G2-round2-report.md",
                         "G2-round3-report.md", "G2-round4-report.md"]
DOCS_ACCEPTANCE_ROUND4 = ["checks.json", "limitations.md", "status.json", "commands.md"]

# Never copied, wherever they appear.
SKIP_DIR_NAMES = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".validation-tmp", ".pytest_cache",
                  ".mypy_cache", ".ruff_cache", ".tmp-pytest", "htmlcov", ".idea", ".vscode", "build", "dist"}
SKIP_DIR_GLOBS = ["*.egg-info"]
SKIP_FILE_GLOBS = ["*.pyc", "*.pyo", ".coverage", "Thumbs.db", "desktop.ini", ".DS_Store", ".env", ".env.*",
                   "*.pem", "*.p12", "*.pfx", "*.key", "credentials.json", "*_credentials.json",
                   "*.sqlite-wal", "*.sqlite-shm", "*.db-wal", "*.db-shm", "*.sqlite-journal", "*.db-journal"]
SKIP_FILE_KEEP = {".env.example"}

EXCLUDED_REASONS = {
    ".git": "version-control metadata of the working repository",
    ".venv": "local Python environment",
    ".pytest_cache": "test cache",
    ".validation-tmp": "scratch space of the G2 validation runs",
    "project_kernel_r1": "older R1 implementation, superseded by src/project_kernel; no published test or module imports it",
    "DELIVERY_PLAN.md": "internal contest work plan: stale status, unchecked boxes and entries the project has voided; "
                         "the panel treats the root plan as optional (absent files are skipped)",
    "scripts": "empty directory",
    "docs/acceptance": "raw G2 evidence (captures, JUnit, scenario archives, zips); only the report summaries and the "
                       "round-4 checks/limitations/status/commands are kept",
    "docs/reviews": "review working papers with local paths; superseded by the retained G2 summaries",
    "docs/handoffs": "agent hand-off notes with local paths and machine names; internal coordination, not product documentation",
    "docs/history": "upstream README snapshot of the parent package",
    "docs/integration": "internal ownership and acceptance log of the parallel build",
    "tools/archive_g2_scenarios.py": "needs the excluded docs/acceptance/G2-round4 tree",
    "tools/build_g2_round4.py": "needs the excluded docs/acceptance and docs/reviews trees",
}
HEAVY_UNMEASURED = {".git", ".venv", ".validation-tmp", ".pytest_cache", "node_modules"}


def _globbed(name: str, patterns) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or _globbed(name, SKIP_DIR_GLOBS)


def skip_file(name: str) -> bool:
    return name not in SKIP_FILE_KEEP and _globbed(name, SKIP_FILE_GLOBS)


def walk_files(base: Path):
    """Yield (relative-to-base posix path, absolute path) for every kept file below base."""
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not skip_dir(d))
        for name in sorted(filenames):
            if not skip_file(name):
                full = Path(dirpath) / name
                yield full.relative_to(base).as_posix(), full


def size_of(path: Path, measure: bool = True) -> int:
    if path.is_file():
        return path.stat().st_size
    if not measure:
        return -1
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def collect(src: Path):
    """Return the ordered list of (destination posix path, source path, area)."""
    picked: list[tuple[str, Path, str]] = []

    def add_file(rel: str, area: str):
        path = src / rel
        if path.is_file():
            picked.append((rel, path, area))

    def add_tree(rel: str, area: str):
        base = src / rel
        if base.is_dir():
            for inner, full in walk_files(base):
                picked.append((f"{rel}/{inner}", full, area))

    for name in sorted(p.name for p in src.iterdir() if p.is_file()):
        if _globbed(name, ["README*.md"]) and name not in ROOT_FILES:
            add_file(name, "root")
    for name in ROOT_FILES:
        add_file(name, "root")
    for name in ROOT_DIRS:
        add_tree(name, name)

    tools = src / "tools"
    if tools.is_dir():
        for entry in sorted(tools.iterdir(), key=lambda p: p.name):
            if entry.is_file() and (entry.name in TOOLS_FILES or _globbed(entry.name, TOOLS_GLOBS)) and not skip_file(entry.name):
                picked.append((f"tools/{entry.name}", entry, "tools"))
        for name in TOOLS_DIRS:
            add_tree(f"tools/{name}", "tools")

    for name in DOCS_FILES:
        add_file(f"docs/{name}", "docs")
    for name in DOCS_DIRS:
        add_tree(f"docs/{name}", "docs")
    for name in DOCS_ACCEPTANCE_FILES:
        add_file(f"docs/acceptance/{name}", "docs/acceptance (summaries)")
    for name in DOCS_ACCEPTANCE_ROUND4:
        add_file(f"docs/acceptance/G2-round4/{name}", "docs/acceptance (summaries)")

    seen = set()
    unique = []
    for item in picked:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    return unique


def excluded_inventory(src: Path, included: set[str]):
    """Describe what exists in the source but is not published, with sizes and reasons."""
    rows = []

    def reason_for(rel: str) -> str:
        if rel in EXCLUDED_REASONS:
            return EXCLUDED_REASONS[rel]
        if rel.endswith(".egg-info"):
            return "generated package metadata"
        return "not on the publish allowlist"

    def add(rel: str):
        path = src / rel
        if not path.exists():
            return
        measure = path.name not in HEAVY_UNMEASURED
        rows.append({"path": rel, "kind": "dir" if path.is_dir() else "file", "bytes": size_of(path, measure),
                     "files": (sum(1 for _ in walk_files(path)) if path.is_dir() and measure else None),
                     "reason": reason_for(rel)})

    for entry in sorted(src.iterdir(), key=lambda p: p.name):
        rel = entry.name
        if any(i == rel or i.startswith(rel + "/") for i in included):
            continue
        add(rel)
    for sub in ("docs", "tools"):
        base = src / sub
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir(), key=lambda p: p.name):
            rel = f"{sub}/{entry.name}"
            if rel == "docs/acceptance":
                inside = sorted(entry.iterdir(), key=lambda p: p.name)
                kept = 0
                for child in inside:
                    crel = f"docs/acceptance/{child.name}"
                    if crel in included or any(i.startswith(crel + "/") for i in included):
                        kept += 1
                total = size_of(entry)
                kept_bytes = sum(os.path.getsize(src / i) for i in included if i.startswith("docs/acceptance/"))
                rows.append({"path": rel + "/ (raw evidence)", "kind": "dir", "bytes": total - kept_bytes,
                             "files": sum(1 for _ in walk_files(entry)) - sum(1 for i in included if i.startswith("docs/acceptance/")),
                             "reason": EXCLUDED_REASONS[rel]})
                continue
            if any(i == rel or i.startswith(rel + "/") for i in included):
                continue
            add(rel)
    return rows


def human(n: int) -> str:
    if n < 0:
        return "n/a"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / 1:.1f} {unit}"
        n /= 1024
    return str(n)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_out(src: Path, out: Path):
    out = out.resolve()
    src = src.resolve()
    if out == src or src.is_relative_to(out) or out.is_relative_to(src):
        raise SystemExit(f"refusing: --out {out} overlaps the source {src}")
    if len(out.parts) < 3:
        raise SystemExit(f"refusing: --out {out} is too close to the filesystem root")
    if (out / ".git").exists():
        raise SystemExit(f"refusing: --out {out} contains .git")
    return out


def build(src: Path, out: Path, report_dir: Path):
    start = time.time()
    out = safe_out(src, out)
    items = collect(src)
    if not items:
        raise SystemExit(f"nothing to publish found under {src}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = []
    areas: dict[str, dict] = {}
    for rel, full, area in items:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(full, target)
        size = target.stat().st_size
        files.append({"path": rel, "bytes": size, "sha256": sha256_of(target), "area": area})
        entry = areas.setdefault(area, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += size
    included = {f["path"] for f in files}
    excluded = excluded_inventory(src, included)
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S%z"), "source": str(src), "tree": str(out),
        "included": {"files": len(files), "bytes": sum(f["bytes"] for f in files), "areas": areas},
        "excluded": excluded, "files": files,
        "required_files_check": {name: (out / name).exists() for name in
                                 ("pyproject.toml", "README.md", "src/project_kernel/__init__.py", "tools/verify_g2_evidence.py",
                                  "docs/modules/registry.json", "docs/records/skills/registry.json",
                                  "adapters/agh-plugin/package.json", "adapters/agh-plugin/client/index.js",
                                  "docs/index.html", "docs/.nojekyll")},
        "seconds": round(time.time() - start, 1),
    }
    (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (report_dir / "MANIFEST.md").write_text(render_manifest(report), encoding="utf-8")
    return report


def render_manifest(report: dict) -> str:
    inc = report["included"]
    lines = ["# Publish tree manifest", "",
             f"Generated {report['generated_at']} from the working repository; the working repository is never modified.",
             f"Tree: {inc['files']} files, {human(inc['bytes'])}.", "",
             "## Included (explicit allowlist)", "", "| Area | Files | Size |", "| --- | ---: | ---: |"]
    for area, info in sorted(inc["areas"].items()):
        lines.append(f"| {area} | {info['files']} | {human(info['bytes'])} |")
    lines += ["", "Everywhere: no __pycache__, *.pyc, *.egg-info, node_modules, virtual environments, caches, .env or key files.", "",
              "## Excluded and why", "", "| Path | Size | Files | Reason |", "| --- | ---: | ---: | --- |"]
    for row in report["excluded"]:
        files = "" if row["files"] is None else row["files"]
        lines.append(f"| `{row['path']}` | {human(row['bytes'])} | {files} | {row['reason']} |")
    lines += ["", "## Required files present", ""]
    lines += [f"- `{name}`: {'yes' if ok else 'MISSING'}" for name, ok in report["required_files_check"].items()]
    lines += ["", "## File list", "", "Path, bytes and SHA-256 of every file are in report.json (`files`).", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", default=DEFAULT_SRC)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args(argv)
    out = Path(args.out)
    report = build(Path(args.src), out, Path(args.report_dir) if args.report_dir else out.resolve().parent)
    print(json.dumps({"files": report["included"]["files"], "bytes": report["included"]["bytes"],
                      "missing": [k for k, v in report["required_files_check"].items() if not v]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
