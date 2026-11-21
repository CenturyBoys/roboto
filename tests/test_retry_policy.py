"""Política de auto-retry vs. terminal (classificar_retry): stall do motor re-tenta 1x; transitório
de provedor re-tenta até o teto; o resto é terminal. Fixa o fix do run #1042 (stall virava mudo)."""

from __future__ import annotations

from roboto.app.pr_cycle import classificar_retry


def test_stall_retenta_uma_vez_depois_terminal() -> None:
    # TimeoutError (idle-timeout) tem str() VAZIO — a política casa no TIPO, não na mensagem.
    exc = TimeoutError()
    detalhe = str(exc).strip() or type(exc).__name__  # "TimeoutError"
    # 1ª falha (attempt=0): re-enfileira (tentativa 1)
    assert classificar_retry(exc, detalhe, 0) == (True, "stall")
    # 2ª falha (attempt=1): já re-tentou 1x → terminal
    assert classificar_retry(exc, detalhe, 1) == (False, "stall")


def test_provedor_transitorio_retenta_ate_o_teto() -> None:
    exc = RuntimeError("API Error: 429 Too Many Requests")
    detalhe = str(exc)
    assert classificar_retry(exc, detalhe, 0) == (True, "provedor")
    assert classificar_retry(exc, detalhe, 1) == (True, "provedor")
    # attempt=2 → nxt=3 == _MAX_RUN_ATTEMPTS → não re-tenta mais
    assert classificar_retry(exc, detalhe, 2) == (False, None)


def test_erro_permanente_e_terminal() -> None:
    exc = ValueError("git push rejected: non-fast-forward")
    assert classificar_retry(exc, str(exc), 0) == (False, None)
