"""Classificação de erro transitório de provedor (Trilha B/H)."""

from __future__ import annotations

from roboto.app.transient import is_transient


def test_402_credit_is_transient() -> None:
    assert is_transient("API Error: 402 ... would exceed your available credit")
    assert is_transient("Error from provider(openrouter: 402)")


def test_rate_limit_and_5xx_transient() -> None:
    assert is_transient("429 Too Many Requests")
    assert is_transient("provider overloaded, try again")
    assert is_transient("503 Service Unavailable")
    assert is_transient("upstream timeout")


def test_permanent_errors_not_transient() -> None:
    assert not is_transient("motor travado: watchdog de inatividade")
    assert not is_transient("git push rejected: non-fast-forward")
    assert not is_transient("KeyError: 'title'")
