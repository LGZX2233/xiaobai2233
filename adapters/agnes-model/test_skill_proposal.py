import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from skill_proposal import draft, write_proposal  # noqa: E402


class FakeModel:
    def __init__(self, data):
        self.data = data
        self.prompts = []

    def generate(self, prompt, schema=None, temperature=0.7):
        self.prompts.append(prompt)
        return {"text": "", "model": "fake", "data": self.data}

    def embed(self, text):
        return []


def _repo(tmp_path):
    (tmp_path / "docs/records/skills").mkdir(parents=True)
    (tmp_path / "skill.md").write_text("method body", encoding="utf-8")
    (tmp_path / "ev.md").write_text("evidence body", encoding="utf-8")
    registry = {"skills": [{"skill_id": "s", "path": "skill.md", "current_version": "1.0.0",
                            "versions": [{"version": "1.0.0",
                                          "evidence_refs": ["ev.md", "gone.md"]}]}]}
    (tmp_path / "docs/records/skills/registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return tmp_path


def test_proposal_is_proposed_and_sanitized(tmp_path):
    root = _repo(tmp_path)
    before = (root / "docs/records/skills/registry.json").read_text(encoding="utf-8")
    model = FakeModel({"dimensions": {
        "correctness": {"score": 2, "evidence": "ev.md"},
        "applicability": {"score": 1, "evidence": ""},
        "reuse_benefit": {"score": 7, "evidence": "x"},
        "maintainability": {"score": 0, "evidence": "ev.md"}},
        "review_suggestion": "none"})
    p = draft(model, root, "s", now=datetime(2026, 10, 14, tzinfo=timezone.utc))
    assert p["status"] == "proposed" and p["requires_human_confirmation"]
    assert p["dimensions"]["correctness"]["score"] == 2
    assert p["dimensions"]["applicability"]["score"] is None
    assert p["dimensions"]["reuse_benefit"]["score"] is None
    assert p["review_suggestion"] == "review_required"
    assert p["missing_evidence_refs"] == ["gone.md"]
    assert "evidence body" in model.prompts[0] and "method body" in model.prompts[0]
    path = write_proposal(root, p)
    assert json.loads(path.read_text(encoding="utf-8"))["skill_id"] == "s"
    assert (root / "docs/records/skills/registry.json").read_text(encoding="utf-8") == before
