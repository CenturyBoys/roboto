"""Triagem de CI: o AGENTE classifica a procedência; a POLÍTICA pura decide a ação."""

from __future__ import annotations

from roboto.app.ci_triage import (
    ACAO_ABRIR_ISSUE,
    ACAO_CORRIGIR,
    ACAO_ESCALAR,
    CAT_CONFIG,
    CAT_INFRA,
    CAT_NOSSO,
    CAT_SEGURANCA,
    CiTriage,
    _parse_triage,
    acao_ci,
    changed_files_from_diff,
    triar_ci,
)
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class _Gw:
    def __init__(self, reply: str, fail: bool = False) -> None:
        self._reply, self._fail = reply, fail

    async def complete(self, messages: list[ChatMessage], tier: Tier) -> Result[Completion, Error]:
        if self._fail:
            return Err(Error("llm", "indisponível"))
        return Ok(Completion(text=self._reply, model="stub"))


_SEC = (
    "CATEGORIA: dependencia_seguranca\nNOSSO: nao\nCONFIANCA: alta\n"
    "TITULO: Vuln HIGH no effect\nRESUMO: bump effect >=3.22.1\nDEDUP: GHSA-7589"
)


def test_parse_extrai_campos() -> None:
    t = _parse_triage(_SEC)
    assert t.categoria == CAT_SEGURANCA
    assert t.nosso is False
    assert t.confianca == "alta"
    assert t.dedup == "GHSA-7589"


def test_parse_categoria_desconhecida_vira_infra() -> None:
    # categoria inválida → infra (conservador: não força correção cega)
    t = _parse_triage("CATEGORIA: sei_la\nNOSSO: nao\nCONFIANCA: alta")
    assert t.categoria == CAT_INFRA


def test_parse_nosso_implicito_por_categoria() -> None:
    t = _parse_triage("CATEGORIA: nosso_codigo\nCONFIANCA: alta")
    assert t.nosso is True  # categoria nosso_codigo força nosso=True mesmo sem o campo


def test_acao_nosso_corrige() -> None:
    assert acao_ci(CiTriage(CAT_NOSSO, True, "alta", "", "", "")) == ACAO_CORRIGIR


def test_acao_seguranca_e_config_abrem_issue() -> None:
    assert acao_ci(CiTriage(CAT_SEGURANCA, False, "alta", "x", "y", "z")) == ACAO_ABRIR_ISSUE
    assert acao_ci(CiTriage(CAT_CONFIG, False, "media", "x", "y", "z")) == ACAO_ABRIR_ISSUE


def test_acao_infra_escala() -> None:
    assert acao_ci(CiTriage(CAT_INFRA, False, "alta", "", "", "")) == ACAO_ESCALAR


def test_acao_baixa_confianca_sempre_escala() -> None:
    # conservador: na dúvida NÃO conserta cego nem abre issue à toa — escala pro humano.
    assert acao_ci(CiTriage(CAT_SEGURANCA, False, "baixa", "x", "y", "z")) == ACAO_ESCALAR
    assert acao_ci(CiTriage(CAT_NOSSO, True, "baixa", "", "", "")) == ACAO_ESCALAR


def test_changed_files_do_diff() -> None:
    diff = (
        "diff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@\n+linha\n"
        "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@\n+doc\n"
    )
    assert changed_files_from_diff(diff) == ["src/x.ts", "README.md"]


async def test_triar_usa_o_agente() -> None:
    t = await triar_ci("✖ scan: high ReDoS effect", ["docs/p.md"], "+++ b/docs/p.md", _Gw(_SEC))
    assert t.categoria == CAT_SEGURANCA and t.nosso is False


async def test_triar_gateway_falha_degrada_conservador() -> None:
    # gateway fora → infra + baixa confiança → a política escala (não chuta correção)
    t = await triar_ci("erro", [], "", _Gw("", fail=True))
    assert t.categoria == CAT_INFRA
    assert acao_ci(t) == ACAO_ESCALAR
