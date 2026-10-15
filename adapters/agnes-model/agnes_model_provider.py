"""Agnes model provider implementing project_kernel.ports.ModelPort.

Lives outside the kernel: the kernel only depends on the port and never calls a
model itself. Configuration comes from the environment, never from source:
AGNES_BASE_URL, AGNES_API_KEY, AGNES_MODEL.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Mapping

Transport = Callable[[str, Mapping[str, str], bytes, float], dict]


def _http_post(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> dict:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class AgnesModelProvider:
    def __init__(self, base_url: str, api_key: str, model: str, *,
                 timeout: float = 60.0, transport: Transport | None = None):
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key and model are required")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._transport = transport or _http_post

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **kwargs: Any) -> "AgnesModelProvider":
        env = os.environ if env is None else env
        missing = [k for k in ("AGNES_BASE_URL", "AGNES_API_KEY", "AGNES_MODEL") if not env.get(k)]
        if missing:
            raise ValueError("missing environment: " + ", ".join(missing))
        return cls(env["AGNES_BASE_URL"], env["AGNES_API_KEY"], env["AGNES_MODEL"], **kwargs)

    def _post(self, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self._api_key}"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._transport(self.base_url + path, headers, body, self.timeout)

    def generate(self, prompt: str, schema: dict[str, Any] | None = None,
                 temperature: float = 0.7) -> dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        if schema is not None:
            messages.insert(0, {"role": "system", "content":
                                "Reply with a single JSON object matching this schema:\n"
                                + json.dumps(schema, ensure_ascii=False)})
        resp = self._post("/chat/completions", {"model": self.model, "messages": messages,
                                                "temperature": temperature})
        text = resp["choices"][0]["message"]["content"]
        result: dict[str, Any] = {"text": text, "model": resp.get("model", self.model)}
        if schema is not None:
            result["data"] = _parse_json_object(text)
        return result

    def embed(self, text: str) -> list[float]:
        resp = self._post("/embeddings", {"model": self.model, "input": text})
        return list(resp["data"][0]["embedding"])

    def __repr__(self) -> str:
        return f"AgnesModelProvider(base_url={self.base_url!r}, model={self.model!r})"


def _parse_json_object(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model reply contains no JSON object")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("model reply JSON is not an object")
    return data
