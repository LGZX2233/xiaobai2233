import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agnes_model_provider import AgnesModelProvider  # noqa: E402

from project_kernel.ports.ports import ModelPort


def _fake(reply: dict, calls: list):
    def transport(url, headers, body, timeout):
        calls.append((url, dict(headers), json.loads(body)))
        return reply
    return transport


def test_generate_with_schema_parses_json_and_satisfies_port():
    calls = []
    reply = {"model": "m", "choices": [{"message": {"content": 'ok {"score": 3, "reason": "x"}'}}]}
    p = AgnesModelProvider("https://example.invalid/v1/", "k", "m", transport=_fake(reply, calls))
    assert isinstance(p, ModelPort)
    out = p.generate("rate", schema={"type": "object"}, temperature=0.1)
    assert out["data"] == {"score": 3, "reason": "x"}
    url, headers, body = calls[0]
    assert url == "https://example.invalid/v1/chat/completions"
    assert headers["Authorization"] == "Bearer k"
    assert body["messages"][0]["role"] == "system" and body["temperature"] == 0.1


def test_embed_and_repr_hides_key():
    calls = []
    p = AgnesModelProvider("https://e.invalid", "secret", "m",
                           transport=_fake({"data": [{"embedding": [0.1, 0.2]}]}, calls))
    assert p.embed("t") == [0.1, 0.2]
    assert "secret" not in repr(p)


def test_from_env_requires_all_settings():
    with pytest.raises(ValueError, match="AGNES_API_KEY"):
        AgnesModelProvider.from_env({"AGNES_BASE_URL": "u", "AGNES_MODEL": "m"})


def test_reply_without_json_is_rejected():
    reply = {"choices": [{"message": {"content": "no json here"}}]}
    p = AgnesModelProvider("u", "k", "m", transport=_fake(reply, []))
    with pytest.raises(ValueError):
        p.generate("x", schema={})
