"""Model-drafted skill assessment proposals.

The model only drafts; output is status "proposed" and never edits the skill
registry. A human reviews the proposal and records the real assessment
(docs/architecture/skill-growth.md: scores are 0/1/2/null, never averaged).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DIMENSIONS = ("correctness", "applicability", "reuse_benefit", "maintainability")
_SHANGHAI = timezone(timedelta(hours=8))

SCHEMA = {
    "type": "object",
    "required": ["dimensions", "counterexamples", "review_suggestion"],
    "properties": {
        "dimensions": {"type": "object", "properties": {
            d: {"type": "object", "required": ["score", "evidence"], "properties": {
                "score": {"enum": [0, 1, 2, None]}, "evidence": {"type": "string"}}}
            for d in DIMENSIONS}},
        "counterexamples": {"type": "array", "items": {"type": "string"}},
        "review_suggestion": {"enum": ["none", "review_required", "undetermined"]},
    },
}


def build_prompt(skill_id: str, version: str, skill_text: str, evidence: dict[str, str]) -> str:
    parts = [
        f"Draft a reuse assessment for skill {skill_id} version {version}.",
        "Score each dimension 0, 1, 2 or null. Use null when the evidence does not observe it.",
        "Do not average, do not score the user, cite the evidence file for every non-null score.",
        "", "## SKILL.md", skill_text,
    ]
    for ref, text in evidence.items():
        parts += ["", f"## Evidence: {ref}", text]
    return "\n".join(parts)


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    dims = data.get("dimensions") or {}
    clean = {}
    for d in DIMENSIONS:
        item = dims.get(d) or {}
        score = item.get("score")
        if score not in (0, 1, 2, None):
            score = None
        evidence = str(item.get("evidence") or "")
        if score is not None and not evidence:
            score = None
        clean[d] = {"score": score, "evidence": evidence}
    suggestion = data.get("review_suggestion")
    if any(v["score"] == 0 for v in clean.values()):
        suggestion = "review_required"
    if suggestion not in ("none", "review_required", "undetermined"):
        suggestion = "undetermined"
    return {"dimensions": clean,
            "counterexamples": [str(c) for c in data.get("counterexamples") or []],
            "review_suggestion": suggestion}


def draft(model: Any, root: Path, skill_id: str, now: datetime | None = None) -> dict[str, Any]:
    registry = json.loads((root / "docs/records/skills/registry.json").read_text(encoding="utf-8"))
    skill = next((s for s in registry["skills"] if s["skill_id"] == skill_id), None)
    if skill is None:
        raise ValueError(f"unknown skill {skill_id!r}")
    version = skill["current_version"]
    entry = next(v for v in skill["versions"] if v["version"] == version)
    evidence = {}
    for ref in entry.get("evidence_refs", []):
        path = root / ref
        if path.is_file():
            evidence[ref] = path.read_text(encoding="utf-8")
    skill_text = (root / skill["path"]).read_text(encoding="utf-8")
    reply = model.generate(build_prompt(skill_id, version, skill_text, evidence),
                           schema=SCHEMA, temperature=0.2)
    now = now or datetime.now(_SHANGHAI)
    return {
        "schema": "skill_assessment_proposal.v1",
        "status": "proposed",
        "requires_human_confirmation": True,
        "skill_id": skill_id,
        "skill_version": version,
        "created_at": now.isoformat(timespec="seconds"),
        "model": reply.get("model"),
        "evidence_refs": sorted(evidence),
        "missing_evidence_refs": sorted(set(entry.get("evidence_refs", [])) - set(evidence)),
        **_validate(reply["data"]),
    }


def write_proposal(root: Path, proposal: dict[str, Any]) -> Path:
    out_dir = root / "docs/records/skills/proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = proposal["created_at"][:19].replace(":", "").replace("-", "")
    path = out_dir / f"{proposal['skill_id']}-{proposal['skill_version']}-{stamp}.json"
    path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    from agnes_model_provider import AgnesModelProvider
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_id")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    proposal = draft(AgnesModelProvider.from_env(), args.root, args.skill_id)
    print(write_proposal(args.root, proposal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
