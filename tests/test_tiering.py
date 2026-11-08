"""Classificador de tier: grande/arquitetural -> forte; resto -> barato (determinístico)."""

from __future__ import annotations

from roboto.app.tiering import classificar_tier, precisa_forte
from roboto.llm.decide import Decision
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


def test_tarefa_pequena_fica_no_barato() -> None:
    d = classificar_tier(
        "feat(web): adicionar link Mapa no rodapé",
        "Adicione um <Link href=/mapa> em site-footer.tsx usando a chave menu.map.",
    )
    assert d.forte is False


def test_muitos_arquivos_vira_forte() -> None:
    # limiar subido p/ 6 (#242): tarefa com MUITOS arquivos citados vai pro forte
    arqs = ", ".join(f"apps/web/src/{c}.tsx" for c in "abcdef")  # 6 arquivos
    d = classificar_tier("feat: refatorar capacidades", f"toca {arqs}")
    assert d.forte is True
    assert "arquivos" in d.motivo


def test_poucos_arquivos_fica_no_barato() -> None:
    # 3 arquivos (antes virava forte) agora fica no barato — o degrau cobre o resgate
    d = classificar_tier(
        "feat: ajuste", "toca apps/web/src/a.tsx, apps/web/src/b.tsx e apps/web/src/c.tsx"
    )
    assert d.forte is False


def test_arquitetural_com_corpo_extenso_vira_forte() -> None:
    corpo = (
        "O ADR 0042 pede uma camada ports/adapters para abstrair capacidades de plataforma. "
        "Precisamos refatorar a detecção e o ciclo de permissão sem duplicação. " * 3
    )
    d = classificar_tier("feat(platform): camada de capacidades", corpo)
    assert d.forte is True


def test_keyword_arquitetural_em_corpo_curto_nao_basta() -> None:
    d = classificar_tier("chore: nota", "pequeno refactor de nome")
    assert d.forte is False


# --- degrau-2 (Jev/decider) sobre o tier ---------------------------------------------------------


class _StubDecider:
    """Decider de teste: devolve uma Decision fixa (ou Err) sem rede."""

    def __init__(self, result: Result[Decision, Error]) -> None:
        self._result = result

    async def decide(self, question: str, context: str) -> Result[Decision, Error]:
        return self._result


async def test_precisa_forte_sem_decider_e_so_deterministico() -> None:
    d = await precisa_forte("chore: nota", "pequeno ajuste de nome", decider=None)
    assert d.forte is False


async def test_precisa_forte_respeita_deterministico_forte_sem_consultar_jev() -> None:
    # determinístico já mandou pro forte (6 arquivos) → nem consulta o Jev
    called = {"n": 0}

    class Spy:
        async def decide(self, q: str, c: str) -> Result[Decision, Error]:
            called["n"] += 1
            return Ok(Decision(False, 1.0))

    arqs = ", ".join(f"apps/web/src/{c}.tsx" for c in "abcdef")
    d = await precisa_forte("feat: refatorar", f"toca {arqs}", decider=Spy())
    assert d.forte is True
    assert called["n"] == 0  # não rebaixa nem consulta quando o keyword já é forte


async def test_precisa_forte_jev_promove_base_para_forte() -> None:
    # determinístico diz base (escopo curto sem keyword), mas o Jev promove com confiança alta
    dec = _StubDecider(Ok(Decision(decision=True, confidence=0.9, reason="refator cross-módulo")))
    d = await precisa_forte("feat: ajuste", "corpo curto", decider=dec)
    assert d.forte is True
    assert "jev" in d.motivo


async def test_precisa_forte_jev_diz_nao_fica_base() -> None:
    dec = _StubDecider(Ok(Decision(decision=False, confidence=0.9)))
    d = await precisa_forte("feat: ajuste", "corpo curto", decider=dec)
    assert d.forte is False


async def test_precisa_forte_jev_confianca_baixa_nao_promove() -> None:
    dec = _StubDecider(Ok(Decision(decision=True, confidence=0.4)))
    d = await precisa_forte("feat: ajuste", "corpo curto", decider=dec, min_confidence=0.6)
    assert d.forte is False


async def test_precisa_forte_jev_erro_cai_no_deterministico() -> None:
    dec = _StubDecider(Err(Error("jev", "falhou")))
    d = await precisa_forte("feat: ajuste", "corpo curto", decider=dec)
    assert d.forte is False  # degrada pro determinístico (não bloqueia)
