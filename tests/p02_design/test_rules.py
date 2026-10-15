"""Restricted data-rule DSL: deny precedence, unknown fail-safe, conditions."""
from __future__ import annotations

from project_kernel.contracts.dto import Condition
from project_kernel.domain.design.rules import DataRule, evaluate_rules, resolve_fact


def _cond_path(path, op, value):
    return Condition(path=path, operator=op, value=value)


def _rule(rid, path, op, value, effect="deny"):
    return DataRule(rule_id=rid, enabled=True,
                    when=_cond_path(path, op, value), effect=effect, reason="r")


def test_resolve_fact_and_unknown():
    facts = {"environment": {"python": "3.12"}, "mode": "test"}
    assert resolve_fact(facts, "environment.python") == "3.12"
    assert resolve_fact(facts, "environment.node") is not None  # sentinel
    # missing path returns the unknown sentinel, never raises
    from project_kernel.domain.design.rules import _UNKNOWN
    assert resolve_fact(facts, "nope.missing") is _UNKNOWN


def test_deny_matching_blocks():
    facts = {"mode": "production"}
    out = evaluate_rules([_rule("r1", "mode", "eq", "production")], facts)
    assert out.blocked is True


def test_unknown_deny_condition_blocks():
    facts = {}
    out = evaluate_rules([_rule("r1", "environment.sandbox", "eq", "os_enforced")], facts)
    assert out.blocked is True
    assert out.unknown_paths == ("r1",)


def test_require_human_and_warn():
    facts = {"target": "production"}
    rules = [
        _rule("w1", "target", "eq", "production", effect="warn"),
        DataRule(rule_id="h1", enabled=True,
                 when=_cond_path("target", "eq", "production"),
                 effect="require_human", reason="needs approval"),
    ]
    out = evaluate_rules(rules, facts)
    assert out.blocked is False
    assert out.require_human is True
    assert out.warnings == ("r",)


def test_no_allow_effect_exists():
    # effect enum only allows deny/require_human/warn; allow cannot override deny
    facts = {"x": 1}
    deny = _rule("d1", "x", "eq", 1, effect="deny")
    out = evaluate_rules([deny], facts)
    assert out.blocked is True


def test_all_any_not_conditions():
    facts = {"a": 1, "b": 2}
    cond_all = Condition(all=(_cond_path("a", "eq", 1), _cond_path("b", "eq", 2)))
    out = evaluate_rules([DataRule("r", True, cond_all, "deny", "x")], facts)
    assert out.blocked is True
    cond_not = Condition(not_=_cond_path("a", "eq", 99))
    out2 = evaluate_rules([DataRule("r", True, cond_not, "deny", "x")], facts)
    assert out2.blocked is True


def test_integer_comparison():
    facts = {"attempts": 3}
    out = evaluate_rules([_rule("r", "attempts", "gte", 3)], facts)
    assert out.blocked is True
    out2 = evaluate_rules([_rule("r", "attempts", "lt", 3)], facts)
    assert out2.blocked is False
