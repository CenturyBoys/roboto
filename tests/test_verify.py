"""Funções puras do verify shift-left (sem subprocesso): filtro TS, parse e seção do PR."""

from __future__ import annotations

from roboto.app.verify import VerifyResult, _introduzidos_de, arquivos_ts, secao_verify


def test_arquivos_ts_filtra_so_typescript() -> None:
    entrada = ["a.ts", "b.tsx", "c.py", "d.md", "e.mts", "f.css"]
    assert arquivos_ts(entrada) == ["a.ts", "b.tsx", "e.mts"]


def test_introduzidos_le_errors_resolved() -> None:
    res = {"errors_resolved": ["x.ts:3 Type 'string' is not assignable to type 'number'.", ""]}
    assert _introduzidos_de(res) == ["x.ts:3 Type 'string' is not assignable to type 'number'."]


def test_secao_ok_quando_sem_erros() -> None:
    md = secao_verify(VerifyResult(True, []))
    assert "✅" in md and "Verify" in md


def test_secao_lista_erros_introduzidos() -> None:
    md = secao_verify(VerifyResult(True, ["x.ts:3 Type 'string'...", "y.ts:9 oops"]))
    assert "2 novo(s) erro" in md
    assert "x.ts:3" in md


def test_secao_indisponivel_degrada() -> None:
    md = secao_verify(VerifyResult(False, detalhe="handshake falhou"))
    assert "indisponível" in md
