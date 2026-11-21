"""Métrica de reuso (Ponytail band): chamadas do código novo que reusam símbolos existentes."""

from __future__ import annotations

from roboto.app.reuse_metric import reuse_stat

_DIFF = (
    "diff --git a/x.py b/x.py\n"
    "--- a/x.py\n+++ b/x.py\n"
    "+def novo():\n"
    "+    existente_helper(1)\n"      # reusa
    "+    outro_novo_sym()\n"          # não existe
    "+    for i in range(3):\n"        # range é genérico → ignorado
    "+        print(i)\n"              # print genérico → ignorado
)


def test_conta_reuso_vs_novo() -> None:
    def has_def(_wd: str, sym: str) -> bool:
        return sym == "existente_helper"

    rs = reuse_stat(_DIFF, "/w", has_def=has_def)
    assert rs.total == 2  # existente_helper + outro_novo_sym (range/print são genéricos)
    assert rs.reused == 1
    assert rs.ratio == 0.5


def test_so_linhas_adicionadas() -> None:
    diff = "--- a/x.py\n+++ b/x.py\n-removida_antiga()\n+mantida()\n"
    vistos = []

    def has_def(_wd: str, sym: str) -> bool:
        vistos.append(sym)
        return False

    reuse_stat(diff, "/w", has_def=has_def)
    assert vistos == ["mantida"]  # a linha '-' não conta


def test_sem_chamadas_zero() -> None:
    rs = reuse_stat("+++ b/x.md\n+# só doc\n", "/w", has_def=lambda _w, _s: True)
    assert rs.total == 0 and rs.ratio == 0.0


def test_busca_que_falha_nao_derruba() -> None:
    def boom(_wd: str, _sym: str) -> bool:
        raise RuntimeError("git fora")

    rs = reuse_stat(_DIFF, "/w", has_def=boom)
    assert rs.reused == 0 and rs.total == 2  # fail-open: conta como não-reusado
