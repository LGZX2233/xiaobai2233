"""G2 approval must retain all frozen item decisions and current behavior evidence."""
import copy
from pathlib import Path
import runpy

import pytest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/verify_g2_evidence.py"))
CHECK = MODULE["_check_adjudications"]


def _valid(root):
    (root / "evidence.json").write_text("{}\n", encoding="utf-8")
    item = {"expect": "frozen requirement", "public_entries": ["kernel.command"], "verdict": "accepted",
            "independent_review": {"reviewer": "separate reviewer", "decision": "accepted"},
            "conditions": [{"condition": "required observation", "observed": "real RPC outcome",
                "evidence": ["evidence.json"], "junit_cases": [{"classname": "tests.acceptance", "name": "test_rpc"}]}]}
    return {"overall_acceptance_approved": True,
            "frozen_criteria": {name: "frozen requirement" for name in MODULE["G2_IDS"]},
            "checks": [{**copy.deepcopy(item), "id": name} for name in sorted(MODULE["G2_IDS"])]}


def test_complete_adjudications_reference_current_passing_evidence(tmp_path):
    assert CHECK(tmp_path, _valid(tmp_path), {("tests.acceptance", "test_rpc")}, {"evidence.json"}) == []


@pytest.mark.parametrize("damage", ["scope", "expectation", "condition", "observation", "evidence", "case", "review", "verdict"])
def test_incomplete_adjudications_cannot_approve_g2(tmp_path, damage):
    checks = _valid(tmp_path)
    item = checks["checks"][0]
    if damage == "scope":
        checks["checks"].pop()
    elif damage == "expectation":
        item["expect"] = "weaker substituted requirement"
    elif damage == "condition":
        item["conditions"] = []
    elif damage == "observation":
        item["conditions"][0]["observed"] = ""
    elif damage == "evidence":
        item["conditions"][0]["evidence"] = ["unretained.json"]
    elif damage == "case":
        item["conditions"][0]["junit_cases"][0]["name"] = "test_not_run"
    elif damage == "review":
        item["independent_review"] = {}
    elif damage == "verdict":
        item["verdict"] = "pending"
    assert CHECK(tmp_path, checks, {("tests.acceptance", "test_rpc")}, {"evidence.json"})
