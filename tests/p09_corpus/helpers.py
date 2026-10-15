"""Shared P09 test helpers (real temp store + explicit scopes)."""
from __future__ import annotations

from project_kernel.contracts import ObjectRef, sha256_digest
from project_kernel.contracts.dto import CommandContext, ResolvedScope
from project_kernel.corpus import DatasetPolicy, Sample, SplitSpec

PROJ = "proj-a"


def scope(capabilities, *, principal="user-1"):
    return ResolvedScope(project_id=PROJ, store_id="store-a", principal_id=principal,
                         capabilities=frozenset(capabilities), mode="test")


def ctx(capabilities, key, *, principal="user-1"):
    return CommandContext(scope=scope(capabilities, principal=principal), command_id="cmd-test",
                          idempotency_key=key, input_hash=sha256_digest({"key": key}))


def policy(**overrides):
    base = {"dataset_id": "ds", "purpose": "evaluation"}
    base.update(overrides)
    return DatasetPolicy(**base)


def spec(**overrides):
    base = {"seed": "7", "train_percent": 60, "eval_percent": 20, "test_percent": 20}
    base.update(overrides)
    return SplitSpec(**base)


def sample(sample_id="s1", *, kind="success", task="t1", input="question", output="answer",
           project=PROJ, refs=None, **overrides):
    source_refs = refs if refs is not None else (
        ObjectRef(project, "attempt", f"attempt-{task}", "rev-1"),)
    fields = {"kind": kind, "group_id": f"{project}:{task}", "source_refs": source_refs,
              "input": input, "output": output, "source_digests": ("a" * 64,),
              "redaction_receipt": "redact-1"}
    fields.update(overrides)
    return Sample(sample_id=sample_id, **fields)
