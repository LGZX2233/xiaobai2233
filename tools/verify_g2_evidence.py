"""Read-only validation of a selected, immutable G2 evidence round."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
G2_IDS = {f"AC{number:02}" for number in (*range(12, 33), 37, 38, 43, 45)}


def _check_adjudications(root: Path, checks: dict, cases: set, manifest_paths: set) -> list[str]:
    """Validate fourth-round item decisions against retained current evidence."""
    problems = []
    items = checks.get("checks", [])
    ids = [item.get("id") for item in items]
    if len(ids) != len(G2_IDS) or set(ids) != G2_IDS:
        problems.append("adjudication scope differs from the 25 frozen G2 items")
    frozen = checks.get("frozen_criteria", {})
    if set(frozen) != G2_IDS:
        problems.append("frozen acceptance criteria are incomplete")
    for item in items:
        identity = str(item.get("id"))
        if not item.get("expect") or not item.get("public_entries"):
            problems.append("missing frozen expectation or public entry: " + identity)
        if item.get("expect") != frozen.get(identity):
            problems.append("frozen expectation differs from adjudication: " + identity)
        if not item.get("independent_review", {}).get("reviewer") or not item.get("independent_review", {}).get("decision"):
            problems.append("missing independent decision: " + identity)
        conditions = item.get("conditions", [])
        if not conditions:
            problems.append("missing condition observations: " + identity)
        for condition in conditions:
            if not condition.get("condition") or not condition.get("observed"):
                problems.append("empty condition observation: " + identity)
            if not condition.get("evidence") or not condition.get("junit_cases"):
                problems.append("missing condition evidence or passing cases: " + identity)
            for evidence in condition.get("evidence", []):
                path = (root / evidence).resolve()
                if evidence not in manifest_paths or not path.is_relative_to(root) or not path.is_file():
                    problems.append("unmanifested condition evidence: " + identity + " -> " + evidence)
            for case in condition.get("junit_cases", []):
                if (case.get("classname"), case.get("name")) not in cases:
                    problems.append("condition case not passed in current JUnit: " + identity)
        if checks.get("overall_acceptance_approved") is True:
            if item.get("verdict") != "accepted" or item.get("independent_review", {}).get("decision") != "accepted":
                problems.append("overall acceptance includes undecided item: " + identity)
    return problems


def _check_capture(root: Path, name: str, *, require_fingerprints: bool) -> list[str]:
    problems = []
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return ["missing or outside root capture: " + name]
    capture = json.loads(path.read_text(encoding="utf-8"))
    if capture.get("exit_code") != 0:
        problems.append("failed capture: " + name)
    output = (root / capture["output"]).resolve()
    if not output.is_relative_to(root) or not output.is_file():
        problems.append("missing or outside root capture output: " + name)
    elif hashlib.sha256(output.read_bytes()).hexdigest() != capture["output_sha256"]:
        problems.append("capture output hash changed: " + name)
    fingerprints = capture.get("validation_files_sha256")
    if require_fingerprints and (not fingerprints or capture.get("validation_files_unchanged") is not True):
        problems.append("capture has no stable input fingerprints: " + name)
    for source, digest in (fingerprints or {}).items():
        source_path = (root / source).resolve()
        if not source_path.is_relative_to(root) or not source_path.is_file():
            problems.append("missing or outside root capture input: " + source)
        elif hashlib.sha256(source_path.read_bytes()).hexdigest() != digest:
            problems.append("capture input hash changed: " + source)
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", help="Relative evidence package under the kernel root")
    args = parser.parse_args()
    current = ROOT / "docs/acceptance/G2/current.json"
    selected = args.evidence_dir
    if selected is None:
        selected = (json.loads(current.read_text(encoding="utf-8"))["evidence_dir"]
                    if current.is_file() else "docs/acceptance/G2")
    package = (ROOT / selected).resolve()
    if not package.is_relative_to(ROOT):
        parser.error("evidence directory must remain under the kernel root")
    manifest = json.loads((package / "artifact-manifest.json").read_text(encoding="utf-8"))
    status = json.loads((package / "status.json").read_text(encoding="utf-8"))
    problems = []
    for run in status.get("validation_runs", []):
        problems.extend(_check_capture(ROOT, run["capture"],
                                       require_fingerprints=run["require_fingerprints"]))
    for entry in manifest["files"]:
        path = (ROOT / entry["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            problems.append("missing or outside root: " + entry["path"])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append("hash changed: " + entry["path"])
    for path in (ROOT / "src").rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in package.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    cases = set()
    xml_paths = status.get("python_tests", {}).get("junit", None)
    paths = ([ROOT / name for name in xml_paths] if xml_paths is not None
             else list((package / "evidence").glob("pytest-*.xml")))
    for path in paths:
        tree = ET.parse(path).getroot()
        for suite in tree.iter("testsuite"):
            if int(suite.attrib.get("failures", 0)) or int(suite.attrib.get("errors", 0)):
                problems.append("failed tests: " + path.name)
        for case in tree.iter("testcase"):
            identity = (case.attrib.get("classname"), case.attrib.get("name"))
            if identity in cases:
                problems.append("duplicate counted test: " + repr(identity))
            if case.find("skipped") is None and case.find("failure") is None and case.find("error") is None:
                cases.add(identity)
    if status.get("round", 0) >= 4:
        checks = json.loads((package / "checks.json").read_text(encoding="utf-8"))
        problems.extend(_check_adjudications(ROOT, checks, cases, {entry["path"] for entry in manifest["files"]}))
        accepted = checks.get("overall_acceptance_approved") is True
        if accepted != (status.get("status") == "accepted_g2"):
            problems.append("G2 state and item acceptance disagree")
    for name in manifest.get("documents", []):
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            problems.append("missing final newline: " + name)
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#")[0]
            target = re.sub(r":\d+$", "", target)
            if target and not (path.parent / target).exists():
                problems.append("broken link: " + name + " -> " + target)
    if status["python_tests"]["distinct_passed"] != len(cases):
        problems.append("test count differs from JUnit")
    from project_kernel.contracts.digest import compute_bundle_digest
    if compute_bundle_digest() != status["contract_digest"]:
        problems.append("frozen contract digest changed")
    result = {"evidence_dir": selected, "files_checked": len(manifest["files"]),
              "python_tests": len(cases), "status": status["status"], "problems": problems}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
