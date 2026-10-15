"""Deterministic lineage split assignment (P09).

Samples are grouped by project + task lineage: every attempt, repair or
conversation-derived sample of one task lands in the same split, so a lineage
can never be spread across train/eval/test just because the samples have
different ids.
"""
from __future__ import annotations

from ..contracts import sha256_digest
from .models import SplitSpec


def lineage_group_id(project_id: str, task_id: str) -> str:
    """Stable group id for one task lineage inside a project."""
    if not project_id or not task_id:
        raise ValueError("project_id and task_id are required")
    return f"{project_id}:{task_id}"


def lineage_key(project_id: str, group_id: str) -> str:
    return f"{project_id}|{group_id}"


def assign_split(spec: SplitSpec, project_id: str, group_id: str) -> str:
    """Stable split bucket for a lineage group; identical inputs always agree."""
    digest = sha256_digest({"group_by": spec.group_by, "seed": str(spec.seed),
                            "lineage": lineage_key(project_id, group_id)})
    bucket = int(digest, 16) % 100
    cumulative = 0
    for name, percent in (("train", int(spec.train_percent)),
                          ("eval", int(spec.eval_percent)),
                          ("test", int(spec.test_percent))):
        cumulative += percent
        if bucket < cumulative:
            return name
    return "test"
