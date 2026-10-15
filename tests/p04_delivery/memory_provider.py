"""Temporary non-file delivery provider for public-service regressions."""
from __future__ import annotations

from typing import Any, Mapping

class MemoryDeliveryProvider:
    """Publish to an isolated in-memory namespace and observe without writing."""

    sink_ids = frozenset({"memory"})

    def __init__(self, storage, *, project_id: str = "proj-a",
                 namespace: str = "reviewed") -> None:
        self.storage = storage
        self.project_id = project_id
        self.namespace = namespace
        self.apply_calls = []
        self.observe_calls = []
        self.published = {}
        self.observation_unavailable = False
        self.observation_updates = {}
        self.publish_effect = True

    def target(self) -> dict[str, str]:
        return {"method": "bundle", "sink_id": "memory",
                "project_id": self.project_id, "namespace": self.namespace}

    def target_matches(self, target: Mapping[str, Any], *, scope_mode: str) -> bool:
        return (target.get("sink_id") in self.sink_ids
                and target.get("project_id") == self.project_id
                and target.get("namespace") == self.namespace)

    def apply(self, manifest, sink_id: str, operation_id: str) -> Mapping[str, Any]:
        self.apply_calls.append((operation_id, sink_id))
        assert sink_id == "memory"
        assert manifest.required_sinks == ("memory",)
        assert manifest.manifest_id == operation_id
        assert manifest.delivery_operation_refs == (operation_id,)
        if self.publish_effect:
            self.published[operation_id] = {
                "manifest": manifest.body(), "digest": manifest.digest(),
                "artifacts": {artifact.sha256: self.storage.open_read(artifact)
                              for artifact in manifest.artifacts}}
        return {"manifest_id": manifest.manifest_id, "sink_id": sink_id,
                "state": "succeeded" if self.publish_effect else "failed",
                "digest": manifest.digest(), "lease_token": operation_id,
                "locator": "memory:" + self.namespace + "/" + operation_id}

    def observe(self, operation_id: str, manifest_id: str,
                expected_digest: str | None, *, provider_state: str | None = None,
                manifest=None):
        self.observe_calls.append(operation_id)
        if self.observation_unavailable:
            raise OSError("isolated provider observation unavailable")
        published = self.published.get(operation_id)
        receipt = {"operation_id": operation_id,
                   "status": "applied" if published else "absent_pending",
                   "execution_terminal": published is not None,
                   "verified_digest": published["digest"] if published else None}
        receipt.update(self.observation_updates)
        return receipt
