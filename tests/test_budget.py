"""Orçamento do fleet (Trilha L): gasto do mês vs teto + alerta."""

from __future__ import annotations

from roboto.app.budget import assess


def test_under_budget_no_alert() -> None:
    b = assess(40.0, 100.0)
    assert b.pct == 0.4 and b.alert is False and b.over is False


def test_alert_at_80_percent() -> None:
    b = assess(80.0, 100.0)
    assert b.alert is True and b.over is False


def test_over_budget() -> None:
    b = assess(120.0, 100.0)
    assert b.pct == 1.2 and b.alert is True and b.over is True


def test_no_cap_never_alerts() -> None:
    b = assess(999.0, 0.0)
    assert b.cap_usd == 0.0 and b.pct == 0.0 and b.alert is False and b.over is False
