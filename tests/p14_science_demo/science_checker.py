"""Independent verifier for the heat-inversion candidate.

Does not trust the solver's own numbers: it recomputes a closed-form reference
from the raw readings and compares with the ground-truth alpha used to
generate them. The readings in the candidate must also match the fixed-seed
dataset, so fabricated inputs fail.
"""
from __future__ import annotations

import json
import math
import statistics

from project_kernel.contracts.dto import ArtifactRef, CheckResult, ObjectRef

import p14_science_demo.heat_data as hd


def closed_form_alpha(readings: list[float]) -> float:
    estimates = [-math.log(y / math.sin(x)) / hd.T_OBS
                 for x, y in zip(hd.sensor_positions(), readings) if y > 0]
    return statistics.median(estimates)


def judge(raw: bytes) -> tuple[bool, str]:
    try:
        data = json.loads(raw)
        fit = float(data["alpha_fit"])
        readings = [float(v) for v in data["readings"]]
    except (ValueError, KeyError, TypeError):
        return False, "malformed result"
    expected = hd.observations()
    if len(readings) != len(expected) or any(abs(a - b) > 1e-12 for a, b in zip(readings, expected)):
        return False, "readings differ from the dataset"
    ref = closed_form_alpha(readings)
    if abs(fit - ref) / ref > hd.REL_TOLERANCE:
        return False, f"fit {fit:.4f} disagrees with closed-form {ref:.4f}"
    if abs(fit - hd.ALPHA_TRUE) / hd.ALPHA_TRUE > hd.REL_TOLERANCE:
        return False, f"fit {fit:.4f} outside tolerance of true {hd.ALPHA_TRUE}"
    return True, "ok"


class HeatCheckProvider:
    def __init__(self, store, storage):
        self.store = store
        self.storage = storage
        self.calls = 0
        self.last_reason = ""

    def run(self, scope, attempt_ref, candidate_manifest_ref, acceptance_refs):
        self.calls += 1
        body = self.store.get_revision(candidate_manifest_ref)["payload"]
        passed = False
        reason = "no artifacts"
        for art in body["artifacts"]:
            passed, reason = judge(self.storage.open_read(ArtifactRef(**art)))
            if not passed:
                break
        self.last_reason = reason
        items = self.store.get_revision(ObjectRef.from_dict(acceptance_refs[0]))["payload"]["acceptance_items"]
        return tuple(CheckResult(i["item_id"], ObjectRef.from_dict(i["recipe_ref"]),
                                 result="pass" if passed else "fail",
                                 candidate_digest=body["candidate_digest"],
                                 evidence_mode="test") for i in items)
