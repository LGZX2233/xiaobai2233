#!/usr/bin/env python3
"""Pre-publication scanner for the public tree (stdlib only, read-only).

Reports, never modifies:
  * secrets (known token formats, private-key blocks, long values assigned to *_KEY/*_TOKEN/*SECRET*/PASSWORD)
  * personal / local paths and personal e-mail addresses, with counts per file and a recommended action
  * broken relative Markdown links (and whether the target exists in the source repo, i.e. was excluded)
  * documents referenced by docs/modules/registry.json and docs/records/skills/registry.json
  * references from included files to excluded areas
  * license inventory

Secret values are never printed: findings show a four-character prefix and the length only.
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import unquote

MAX_SCAN_BYTES = 8 * 1024 * 1024

# ---------------------------------------------------------------- secrets
SECRET_FORMATS = [
    ("cpk-", re.compile(r"\bcpk-[A-Za-z0-9_\-]{16,}")),
    ("sk-", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("ghp_", re.compile(r"\bghp_[A-Za-z0-9]{30,}")),
    ("github_pat_", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}")),
    ("gho_/ghs_/ghu_", re.compile(r"\bgh[ous]_[A-Za-z0-9]{30,}")),
    ("AKIA", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key block", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{32,}")),
]
ASSIGNMENT = re.compile(
    r"""(?P<key>[A-Za-z0-9_]*(?:_KEY|_TOKEN|SECRET|PASSWORD)[A-Za-z0-9_]*)["']?\s*[=:]\s*["']?(?P<val>[A-Za-z0-9_\-+=.]{20,})""",
    re.IGNORECASE,
)
PLACEHOLDER_HINTS = ("example", "your_", "your-", "changeme", "redacted", "xxxx", "placeholder", "<", "sample", "dummy", "fake")

# ------------------------------------------------------------ local paths
# Patterns are assembled from pieces so that this file does not trip its own scan.
_SEP = r"(?:\\\\|\\|/)+"
_TAIL = r"[^\s\"'`)<>|]*"
PATH_KINDS = [
    ("C: drive user profile", re.compile(r"[Cc]:" + _SEP + "Us" + "ers" + _SEP + _TAIL)),
    ("D: drive contest folder", re.compile(r"[Dd]:" + _SEP + "bi" + "sai" + _TAIL)),
    ("D: drive kernel folder", re.compile(r"[Dd]:" + _SEP + "deepseek" + "hannes" + _TAIL)),
    ("sandbox session path", re.compile("/ses" + "sions/[a-z]+-[a-z]+-[a-z]+[A-Za-z0-9_\\-/.]*")),
    ("sandbox session path (other)", re.compile("/ses" + "sions/(?![a-z]+-[a-z]+-[a-z]+)[A-Za-z0-9_\\-/.{}$]*")),
    ("local user name", re.compile("xiaobai" + "ai")),
]
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
EMAIL_IGNORE_SUFFIX = (".js", ".mjs", ".json", ".md", ".py", ".png", ".jpg", ".svg", ".css", ".ts", ".jsx", ".html", ".txt")
EMAIL_IGNORE_DOMAIN = ("example.com", "example.org", "users.noreply.github.com", "noreply.github.com", "anthropic.com")

LINK = re.compile(r"(?<!\\)\[(?:[^\]\n]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
LINK_DEF = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.MULTILINE)
FENCE = re.compile(r"(^|\n)(```|~~~).*?(\n\2[^\n]*|\Z)", re.DOTALL)
INLINE = re.compile(r"`[^`\n]*`")


def _blank(match: re.Match) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def iter_files(tree: Path):
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames[:] = sorted(d for d in dirnames if d not in (".git", "node_modules"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            yield path.relative_to(tree).as_posix(), path


def read_text(path: Path):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_SCAN_BYTES or b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "replace")


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def mask(value: str) -> str:
    return f"{value[:4]}...({len(value)} chars)"


def context(text: str, start: int, end: int, width: int = 40) -> str:
    snippet = text[max(0, start - width): min(len(text), end + width)]
    return " ".join(snippet.split())[:140]


def scan_secrets(texts: dict[str, str]) -> list[dict]:
    findings = []
    for rel, text in texts.items():
        for label, pattern in SECRET_FORMATS:
            for match in pattern.finditer(text):
                findings.append({"file": rel, "line": line_of(text, match.start()), "kind": label, "severity": "high",
                                 "masked": "private key block" if "PRIVATE" in label else mask(match.group(0))})
        for match in ASSIGNMENT.finditer(text):
            value = match.group("val")
            low = value.lower()
            if any(hint in low for hint in PLACEHOLDER_HINTS):
                continue
            if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
                continue
            findings.append({"file": rel, "line": line_of(text, match.start()), "kind": "assignment to " + match.group("key"),
                             "severity": "review", "masked": mask(value)})
    return findings


def recommend(rel: str) -> str:
    if rel.startswith(("tests/", "fixtures/", "adapters/agnes-model/test_")):
        return "test/fixture: keep if the value is synthetic, otherwise swap for a neutral placeholder"
    if rel.startswith("docs/submission/"):
        return "scrub before submission: judges read this file"
    if rel.startswith("evidence/"):
        return "evidence record: keep if it documents a real run, but consider replacing the user name with <user>"
    if rel.endswith("client/index.js"):
        return "built bundle: fix the source (client/src/i18n/messages.js) and rebuild with npm run build"
    if rel.endswith((".mjs", ".py", ".ps1", ".js")):
        return "code: replace with a relative path or an environment variable"
    if rel.startswith("docs/") or rel.endswith(".md"):
        return "document: replace with <repo> / <user-dir> placeholder unless it is historical and must stay verbatim"
    return "review and replace with a placeholder"


def scan_paths_and_emails(texts: dict[str, str]):
    paths: dict[str, dict] = {}
    emails: dict[str, dict] = {}
    for rel, text in texts.items():
        for kind, pattern in PATH_KINDS:
            for match in pattern.finditer(text):
                entry = paths.setdefault(rel, {"file": rel, "total": 0, "kinds": {}, "samples": [], "recommended_action": recommend(rel)})
                entry["total"] += 1
                entry["kinds"][kind] = entry["kinds"].get(kind, 0) + 1
                if len(entry["samples"]) < 3:
                    entry["samples"].append({"line": line_of(text, match.start()), "text": context(text, match.start(), match.end())})
        for match in EMAIL.finditer(text):
            address = match.group(0)
            lowered = address.lower()
            if lowered.endswith(EMAIL_IGNORE_SUFFIX) or any(lowered.endswith("@" + d) or lowered.endswith("." + d) for d in EMAIL_IGNORE_DOMAIN):
                continue
            entry = emails.setdefault(rel, {"file": rel, "total": 0, "addresses": []})
            entry["total"] += 1
            if address not in entry["addresses"] and len(entry["addresses"]) < 3:
                entry["addresses"].append(address)
    return sorted(paths.values(), key=lambda e: (-e["total"], e["file"])), sorted(emails.values(), key=lambda e: e["file"])


def iter_links(text: str):
    stripped = FENCE.sub(_blank, text)
    stripped = INLINE.sub(_blank, stripped)
    for match in LINK.finditer(stripped):
        yield line_of(stripped, match.start()), match.group(1)
    for match in LINK_DEF.finditer(stripped):
        yield line_of(stripped, match.start()), match.group(1)


def check_links(tree: Path, texts: dict[str, str], src: Path | None) -> list[dict]:
    broken = []
    for rel, text in texts.items():
        if not rel.endswith(".md"):
            continue
        base = posixpath.dirname(rel)
        for line, target in iter_links(text):
            if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", target) or target.startswith("#") or target.startswith("//"):
                continue
            clean = unquote(target.split("#", 1)[0].split("?", 1)[0]).replace("\\", "/")
            if not clean:
                continue
            resolved = posixpath.normpath(clean.lstrip("/") if clean.startswith("/") else posixpath.join(base, clean))
            if resolved.startswith(".."):
                status = "outside_tree"
            elif (tree / resolved).exists():
                continue
            elif src is not None and (src / resolved).exists():
                status = "excluded_from_tree"
            else:
                status = "missing_in_source"
            broken.append({"file": rel, "line": line, "target": target, "resolved": resolved, "status": status})
    return broken


def _strings(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _strings(value)
    elif isinstance(obj, str):
        yield obj


def check_registries(tree: Path) -> dict:
    result = {}
    for registry_rel, bases in (("docs/modules/registry.json", ["docs/modules"]),
                                ("docs/records/skills/registry.json", ["", "docs/records/skills"])):
        path = tree / registry_rel
        entry = {"registry": registry_rel, "present": path.is_file(), "referenced": 0, "missing": []}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as error:
                entry["error"] = str(error)
                data = {}
            for value in sorted(set(_strings(data))):
                if not re.search(r"\.(md|json|mjs|py)$", value) or value.startswith(("http", "#")) or " " in value:
                    continue
                entry["referenced"] += 1
                if not any((tree / base / value).exists() for base in bases):
                    entry["missing"].append(value)
        result[registry_rel] = entry
    return result


def license_inventory(tree: Path, remote_dir: Path | None) -> dict:
    inventory = {"license_files": [], "remote_license": None, "declarations": [], "mismatch": False, "recommendation": ""}
    for rel, path in iter_files(tree):
        if re.match(r"(?i)^(.*/)?(licen[sc]e|copying)(\.[a-z]+)?$", rel):
            inventory["license_files"].append(rel)
    if remote_dir and (remote_dir / "LICENSE").is_file():
        lines = (remote_dir / "LICENSE").read_text(encoding="utf-8", errors="replace").splitlines()
        inventory["remote_license"] = {"title": lines[0].strip() if lines else "", "copyright": next((l.strip() for l in lines if "Copyright" in l), "")}

    def add(where, value):
        inventory["declarations"].append({"where": where, "value": value})

    pyproject = tree / "pyproject.toml"
    if pyproject.is_file():
        match = re.search(r"^license\s*=\s*(.+)$", pyproject.read_text(encoding="utf-8"), re.MULTILINE)
        add("pyproject.toml", match.group(1).strip() if match else "(none)")
    for package in sorted(tree.glob("**/package.json")):
        if "node_modules" in package.parts:
            continue
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
        except ValueError:
            continue
        add(package.relative_to(tree).as_posix(), data.get("license", "(none)"))
    for readme in ("README.md", "README.en.md"):
        text = read_text(tree / readme) if (tree / readme).is_file() else None
        if text:
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(r"(?i)licen[sc]e|许可|授权|版权", line):
                    add(f"{readme}:{number}", line.strip()[:120])
    normalized = set()
    for item in inventory["declarations"]:
        if ":" in item["where"] and item["where"].startswith("README"):
            continue
        text = str(item["value"]).lower()
        normalized.add("proprietary" if "proprietary" in text else "apache-2.0" if "apache" in text else "mit" if "mit" in text else text)
    if inventory["remote_license"] and "mit" in inventory["remote_license"]["title"].lower():
        normalized.add("mit")
    inventory["mismatch"] = len(normalized) > 1
    inventory["normalized"] = sorted(normalized)
    if inventory["mismatch"]:
        inventory["recommendation"] = (
            "The published repository carries an MIT LICENSE, pyproject.toml says Proprietary and the AGH plugin package.json says "
            "Apache-2.0. Recommendation (owner decides): keep the existing MIT LICENSE (publish.ps1 never overwrites it) and align "
            "pyproject.toml and adapters/agh-plugin/package.json to MIT, or consciously choose another licence for all three.")
    return inventory


def excluded_references(texts: dict[str, str], needles: list[str]) -> dict:
    out = {}
    for needle in needles:
        files = {rel: text.count(needle) for rel, text in texts.items() if needle in text}
        out[needle] = {"files": len(files), "occurrences": sum(files.values()),
                       "top": sorted(files.items(), key=lambda kv: -kv[1])[:8]}
    return out


def scan(tree: Path, src: Path | None = None, remote_dir: Path | None = None, excluded_needles: list[str] | None = None) -> dict:
    texts = {}
    for rel, path in iter_files(tree):
        text = read_text(path)
        if text is not None:
            texts[rel] = text
    paths, emails = scan_paths_and_emails(texts)
    secrets = scan_secrets(texts)
    broken = check_links(tree, texts, src)
    registries = check_registries(tree)
    licence = license_inventory(tree, remote_dir)
    refs = excluded_references(texts, excluded_needles or [])
    by_status = {}
    for item in broken:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
    return {
        "tree": str(tree), "text_files_scanned": len(texts),
        "summary": {
            "secrets_high": sum(1 for s in secrets if s["severity"] == "high"),
            "secrets_review": sum(1 for s in secrets if s["severity"] == "review"),
            "files_with_local_paths": len(paths), "local_path_occurrences": sum(e["total"] for e in paths),
            "files_with_emails": len(emails), "email_occurrences": sum(e["total"] for e in emails),
            "broken_links": len(broken), "broken_links_by_status": by_status,
            "registry_missing": sum(len(e["missing"]) for e in registries.values()),
            "license_mismatch": licence["mismatch"],
        },
        "secrets": secrets, "local_paths": paths, "emails": emails, "broken_links": broken,
        "registries": registries, "license": licence, "references_to_excluded": refs,
    }


def render_md(report: dict, limit: int = 60) -> str:
    s = report["summary"]
    lines = ["# Publish tree scan", "", f"Tree: `{report['tree']}`  Text files scanned: {report['text_files_scanned']}", "",
             "| Check | Result |", "| --- | --- |",
             f"| Secrets in known formats (cpk-, sk-, ghp_, github_pat_, AKIA, private keys) | {s['secrets_high']} |",
             f"| Long values assigned to *_KEY / *_TOKEN / *SECRET* / PASSWORD (to review) | {s['secrets_review']} |",
             f"| Local/personal path occurrences | {s['local_path_occurrences']} in {s['files_with_local_paths']} files |",
             f"| E-mail addresses | {s['email_occurrences']} in {s['files_with_emails']} files |",
             f"| Broken relative Markdown links | {s['broken_links']} {s['broken_links_by_status']} |",
             f"| Registry-referenced documents missing | {s['registry_missing']} |",
             f"| Licence declarations disagree | {s['license_mismatch']} |", ""]
    lines += ["## Secrets", ""]
    if report["secrets"]:
        for item in report["secrets"][:limit]:
            lines.append(f"- {item['severity']}: `{item['file']}`:{item['line']} {item['kind']} {item['masked']}")
    else:
        lines.append("None found.")
    lines += ["", "## Local and personal paths (recommend scrubbing)", ""]
    for item in report["local_paths"][:limit]:
        kinds = ", ".join(f"{k} x{v}" for k, v in item["kinds"].items())
        lines.append(f"- `{item['file']}`: {item['total']} ({kinds}). Action: {item['recommended_action']}")
    if len(report["local_paths"]) > limit:
        lines.append(f"- ... {len(report['local_paths']) - limit} more files in scan.json")
    lines += ["", "## E-mail addresses", ""]
    lines += [f"- `{e['file']}`: {e['total']} ({', '.join(e['addresses'])})" for e in report["emails"][:limit]] or ["None found."]
    lines += ["", "## Broken relative Markdown links", ""]
    if report["broken_links"]:
        per_file: dict[str, int] = {}
        for item in report["broken_links"]:
            per_file[item["file"]] = per_file.get(item["file"], 0) + 1
        lines.append("excluded_from_tree = the target exists in the working repo but is not published; missing_in_source = missing there too.")
        lines.append("")
        for status in ("missing_in_source", "outside_tree", "excluded_from_tree"):
            subset = [i for i in report["broken_links"] if i["status"] == status]
            if subset:
                lines.append(f"### {status}: {len(subset)}")
                for item in subset[:limit]:
                    lines.append(f"- `{item['file']}`:{item['line']} -> `{item['target']}`")
                if len(subset) > limit:
                    lines.append(f"- ... {len(subset) - limit} more in scan.json")
    else:
        lines.append("None.")
    lines += ["", "## Documents referenced by the registries", ""]
    for entry in report["registries"].values():
        lines.append(f"- `{entry['registry']}`: present={entry['present']}, referenced={entry['referenced']}, missing={entry['missing']}")
    lines += ["", "## References from published files to excluded areas", ""]
    for needle, info in report["references_to_excluded"].items():
        top = ", ".join(f"`{f}` x{n}" for f, n in info["top"][:4])
        lines.append(f"- `{needle}`: {info['occurrences']} in {info['files']} files. {top}")
    lic = report["license"]
    lines += ["", "## Licence inventory", "", f"- Licence files in tree: {lic['license_files'] or 'none (the remote repository supplies LICENSE)'}",
              f"- Remote LICENSE: {lic['remote_license']}"]
    lines += [f"- {d['where']}: {d['value']}" for d in lic["declarations"]]
    lines += [f"- Mismatch: {lic['mismatch']} ({lic.get('normalized')})", f"- {lic['recommendation']}", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tree")
    parser.add_argument("--src", default=None, help="working repo, used to classify broken links")
    parser.add_argument("--remote-dir", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--md", default=None)
    args = parser.parse_args(argv)
    report = scan(Path(args.tree), Path(args.src) if args.src else None, Path(args.remote_dir) if args.remote_dir else None,
                  ["project_kernel_r1", "DELIVERY_PLAN.md", "docs/acceptance", "docs/handoffs", "docs/reviews", "docs/history", "docs/integration"])
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    markdown = render_md(report)
    if args.md:
        Path(args.md).write_text(markdown, encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
