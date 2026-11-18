"""Testes da policy de 2 eixos (#267, app.policy.verdict)."""

from __future__ import annotations

from roboto.app.policy import (
    ActionKind,
    ActionMode,
    Autonomy,
    Policy,
    ToolClass,
    verdict,
)

_PUSH = frozenset({ActionKind.PUSH})
_MERGE = frozenset({ActionKind.MERGE})
_COMMIT = frozenset({ActionKind.COMMIT})
_NONE: frozenset[ActionKind] = frozenset()


def test_read_runs() -> None:
    assert verdict(ToolClass.READ, _NONE, Policy(Autonomy.CAREFUL)).run


def test_push_gates_on_normal_but_autos_on_free() -> None:
    assert verdict(ToolClass.WRITE, _PUSH, Policy(Autonomy.NORMAL)).ask
    assert verdict(ToolClass.WRITE, _PUSH, Policy(Autonomy.FREE)).run


def test_commit_autos_from_normal() -> None:
    assert verdict(ToolClass.WRITE, _COMMIT, Policy(Autonomy.NORMAL)).run
    assert verdict(ToolClass.WRITE, _COMMIT, Policy(Autonomy.CAREFUL)).ask


def test_merge_always_asks_even_on_free() -> None:
    assert verdict(ToolClass.WRITE, _MERGE, Policy(Autonomy.FREE)).ask
    assert verdict(ToolClass.WRITE, _MERGE, Policy(Autonomy.NORMAL)).ask


def test_high_risk_always_asks_even_on_free() -> None:
    decision = verdict(ToolClass.WRITE, _NONE, Policy(Autonomy.FREE), high_risk=True)
    assert decision.ask
    assert decision.why == "risk"


def test_outside_guard_asks_outbound_after_external_content() -> None:
    # push autoriza sozinho no FREE, mas depois de ler conteúdo externo volta a pedir.
    assert verdict(ToolClass.WRITE, _PUSH, Policy(Autonomy.FREE), outside=True).ask


def test_explicit_rule_overrides_level() -> None:
    policy = Policy(Autonomy.FREE, rules={ActionKind.PUSH: ActionMode.OFF})
    decision = verdict(ToolClass.WRITE, _PUSH, policy)
    assert decision.off


def test_careful_write_asks() -> None:
    assert verdict(ToolClass.WRITE, _NONE, Policy(Autonomy.CAREFUL)).ask
    assert verdict(ToolClass.WRITE, _NONE, Policy(Autonomy.NORMAL)).run


def test_sensitive_asks() -> None:
    assert verdict(ToolClass.SENSITIVE, _NONE, Policy(Autonomy.FREE)).ask
