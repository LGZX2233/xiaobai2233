"""Restricted data-rule DSL (P02). No exec/eval, no Python code.

A rule is a declarative condition over a fact bundle plus an effect
(deny / require_human / warn). Facts are resolved only through declared paths.
An unknown fact never passes a deny rule (fail-safe); there is no "allow" effect
that can override a deny.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...contracts.dto import Condition
from ...contracts.errors import invalid_input


@dataclass(frozen=True)
class DataRule:
    rule_id: str
    enabled: bool
    when: Condition
    effect: str
    reason: str


@dataclass(frozen=True)
class RuleEvaluation:
    blocked: bool
    require_human: bool
    warnings: tuple[str, ...] = ()
    unknown_paths: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.blocked and not self.require_human


_UNKNOWN = object()


def resolve_fact(facts: dict[str, Any], path: str) -> Any:
    """Resolve a dotted path within the fact bundle; returns a sentinel when
    missing (never raises, never evaluates arbitrary expressions)."""
    if not path or any(part == "" for part in path.split(".")):
        raise invalid_input(f"invalid fact path {path!r}")
    cur: Any = facts
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _UNKNOWN
    return cur


def _compare(fact: Any, operator: str, value: Any) -> bool:
    if operator == "eq":
        return fact == value
    if operator == "ne":
        return fact != value
    if operator == "exists":
        return fact is not _UNKNOWN and fact is not None
    if operator == "in":
        return isinstance(value, list) and fact in value
    if operator == "not_in":
        return isinstance(value, list) and fact not in value
    if operator in ("gt", "gte", "lt", "lte"):
        try:
            f, v = float(fact), float(value)
        except (TypeError, ValueError):
            raise invalid_input(f"non-numeric comparison on {fact!r} vs {value!r}")
        return {"gt": f > v, "gte": f >= v, "lt": f < v, "lte": f <= v}[operator]
    raise invalid_input(f"unknown operator {operator!r}")


def evaluate_condition(cond: Condition, facts: dict[str, Any]) -> bool | None:
    """Returns True/False, or None for unknown (fail-safe at the rule level)."""
    if cond.all is not None:
        results = [evaluate_condition(c, facts) for c in cond.all]
        if any(r is False for r in results):
            return False
        if any(r is None for r in results):
            return None
        return True
    if cond.any is not None:
        results = [evaluate_condition(c, facts) for c in cond.any]
        if any(r is True for r in results):
            return True
        if all(r is False for r in results):
            return False
        return None
    if cond.not_ is not None:
        r = evaluate_condition(cond.not_, facts)
        return None if r is None else (not r)
    if cond.path is not None:
        fact = resolve_fact(facts, cond.path)
        if fact is _UNKNOWN:
            return None
        return _compare(fact, cond.operator, cond.value)
    raise invalid_input("condition has no variant")


def evaluate_rules(rules: list[DataRule], facts: dict[str, Any]) -> RuleEvaluation:
    blocked = False
    require_human = False
    warnings: list[str] = []
    unknown_paths: list[str] = []
    decisions: list[str] = []

    for rule in rules:
        if not rule.enabled:
            continue
        result = evaluate_condition(rule.when, facts)
        if rule.effect == "deny":
            if result is True:
                blocked = True
                decisions.append(f"deny:{rule.rule_id}")
            elif result is None:
                # unknown never passes a deny rule
                blocked = True
                unknown_paths.append(rule.rule_id)
                decisions.append(f"deny-unknown:{rule.rule_id}")
        elif rule.effect == "require_human":
            if result is True or result is None:
                require_human = True
                decisions.append(f"require_human:{rule.rule_id}")
        elif rule.effect == "warn":
            if result is True:
                warnings.append(rule.reason)
        else:
            raise invalid_input(f"unknown rule effect {rule.effect!r}")

    return RuleEvaluation(blocked=blocked, require_human=require_human,
                          warnings=tuple(warnings), unknown_paths=tuple(unknown_paths),
                          decisions=tuple(decisions))
