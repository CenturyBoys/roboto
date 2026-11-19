"""Testes do right-sizing semântico (#297/#239 revisão): sinal melhor que contar critérios."""

from __future__ import annotations

from roboto.app.epic_signal import EpicVerdict, assess_epic, epic_advisory, epic_signal
from roboto.llm.decide import Decision
from roboto.orchestrator.model import Error
from roboto.result import Ok, Result


class _FakeDecider:
    def __init__(self, decision: bool, confidence: float, reason: str = "entrega A, B e C") -> None:
        self._d = Decision(decision=decision, confidence=confidence, reason=reason)

    async def decide(self, question: str, context: str) -> Result[Decision, Error]:
        return Ok(self._d)


# feature COESA com 9 critérios (como o #297) — NÃO é épico.
_COESO = "Investigar ownership de região crítica.\n## Critérios de aceite\n" + "".join(
    f"- [ ] item {i}\n" for i in range(9)
)
_EPICO = (
    "## Escopo\n- Implementar o modelo X\n- Criar o scheduler\n- Adicionar notificações\n"
    "Fase 1: modelo. Fase 2: scheduler.\nmexe em migrations, api e ui."
)
_AMBIGUO = "Implementar o worker de imagens expondo uma api nova."


def test_tier0_coeso_com_muitos_criterios_e_small() -> None:
    assert epic_signal("feat: ownership", _COESO).bucket == "small"  # #297: não-épico


def test_tier0_multi_entregavel_vai_pro_jev_nao_afirma() -> None:
    # Tier 0 NÃO afirma épico (nem no multi-entregável): manda pro Jev decidir (ambiguous).
    assert epic_signal("feat: torneio", _EPICO).bucket == "ambiguous"


def test_task_de_analise_e_small() -> None:
    # #297: "Analisar X" = 1 entregável (o estudo) → NUNCA épico, mesmo tocando vários paths.
    body = "Analisar o chaveamento tocando apps/realtime, packages/db e migrations em fases."
    assert epic_signal("Analisar otimização de chaveamento de torneios", body).bucket == "small"


def test_raizes_de_monorepo_nao_contam_como_subsistema() -> None:
    # apps/ e packages/ sozinhos não inflam o sinal (eram o falso-positivo do #297).
    assert epic_signal("feat: x", "muda apps/realtime e packages/db").bucket == "small"


def test_tier0_borderline_e_ambiguous() -> None:
    assert epic_signal("feat: worker", _AMBIGUO).bucket == "ambiguous"


async def test_assess_small_nao_e_epico_sem_jev() -> None:
    v = await assess_epic("feat: ownership", _COESO, None)
    assert v.is_epic is False and v.source == "heuristica"


async def test_assess_ambiguo_usa_jev() -> None:
    v = await assess_epic("feat: worker", _AMBIGUO, _FakeDecider(True, 0.9))  # type: ignore[arg-type]
    assert v.is_epic is True and v.source == "jev"
    assert epic_advisory(v)  # surfa com confiança alta


async def test_assess_ambiguo_sem_decider_e_conservador() -> None:
    v = await assess_epic("feat: worker", _AMBIGUO, None)
    assert v.is_epic is False  # sem Jev no ambíguo → não trava à toa


def test_advisory_vazio_sem_epico_ou_conf_baixa() -> None:
    assert epic_advisory(EpicVerdict(False, 0.9, "x", "jev")) == ""
    assert epic_advisory(EpicVerdict(True, 0.4, "x", "jev")) == ""  # confiança baixa não age
