"""Classificador de erro operacional do provider (billing/cota/rate) → mensagem clara, não opaca."""

from __future__ import annotations

from roboto.app.provider_errors import classify_provider_error

_OPENROUTER_403 = (
    'API Error: 403 Error from provider(openrouter,google/gemini-3.1-flash-lite: 403): '
    '{"error":{"message":"Workspace weekly budget of $40.00 exceeded.","code":403,'
    '"metadata":{"limit_source":"openrouter_workspace_budget","scope":"workspace",'
    '"limit_usd":40,"spend_usd":40.105902834,"resets_at":"2026-11-09T00:00:00.000Z"}}}'
)


def test_classifica_budget_de_workspace_com_detalhes() -> None:
    msg = classify_provider_error(_OPENROUTER_403)
    assert msg is not None
    assert "budget do workspace esgotado" in msg
    assert "$40.11/$40" in msg  # gasto/limite extraídos
    assert "2026-11-09" in msg  # reset extraído
    assert "OPERACIONAL" in msg


def test_classifica_402_sem_credito() -> None:
    msg = classify_provider_error("API Error: 402 This request would exceed your available credit")
    assert msg is not None and "sem crédito" in msg


def test_classifica_429_rate_limit() -> None:
    msg = classify_provider_error("429 rate limit exceeded")
    assert msg is not None and "rate-limit" in msg
    assert classify_provider_error("provider overloaded") is not None


def test_erro_normal_nao_e_operacional() -> None:
    # erro de código/hook não vira mensagem operacional (fica None → feed mostra o erro cru)
    assert classify_provider_error("git -c falhou (code 1): prettier --check") is None
    assert classify_provider_error("motor não editou nada") is None
