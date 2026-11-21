"""Juiz de benchmark AUTO-VALIDADO (a joia do Ponytail `benchmarks/agentic`).

Um LLM-judge só é confiável se passar num SELF-TEST **antes** de gastar API: ele TEM que dar nota
MAIOR para uma referência deliberadamente over-engineered do que para a mínima que resolve. Se não
passar, a gente NÃO confia no veredito (levanta erro em vez de pontuar). Modelo fixo + temp 0 +
rubrica + cada score NOMEIA o construto desnecessário. É o anti-padrão do "LLM-judge que a gente
confia cego" — casa com [[determinismo-primeiro]] e [[diagnostico-modelo-forte-vs-harness]].

Primeiro incremento: o JUIZ (a parte difícil/valiosa). O runner de 39 tarefas × N runs é follow-up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from roboto.llm.port import ChatMessage, ModelGateway, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

JUDGE_SYSTEM = (
    "Você julga ENGENHARIA EXCESSIVA (over-engineering) de um trecho de código. Nota 0-10: "
    "0 = o mínimo que resolve; 10 = cheio de abstração/opção/config/camada que ninguém pediu. "
    "Julgue só o excesso, não o estilo. Responda EXATAMENTE:\n"
    "NOTA: <inteiro 0-10>\n"
    "CONSTRUTO: <o item CONCRETO desnecessário que mais pesou (ex.: 'factory com 1 produto'), "
    "ou 'nenhum'>\n"
    "Regra: sem o CONSTRUTO nomeado, a nota é inválida."
)

# referências do self-test: a OVER tem que pontuar acima da MIN, senão o juiz não discrimina.
_SELFTEST_MIN = "def add(a, b):\n    return a + b"
_SELFTEST_OVER = (
    "class AbstractAdderFactory:\n"
    "    def create(self): return Adder()\n"
    "class Adder:\n"
    "    def __init__(self, strategy=None): self.s = strategy or SumStrategy()\n"
    "    def add(self, a, b): return self.s.apply(a, b)\n"
    "class SumStrategy:\n"
    "    def apply(self, a, b): return a + b"
)


@dataclass(frozen=True)
class JudgeScore:
    nota: float
    construto: str


def _parse(text: str) -> JudgeScore | None:
    campos: dict[str, str] = {}
    for ln in text.splitlines():
        if ":" in ln:
            k, _, v = ln.partition(":")
            campos[k.strip().lower()] = v.strip()
    m = re.search(r"-?\d+(?:\.\d+)?", campos.get("nota", ""))
    construto = campos.get("construto", "").strip()
    if m is None or not construto:  # score sem construto nomeado = inválido (rubrica)
        return None
    return JudgeScore(nota=max(0.0, min(10.0, float(m.group()))), construto=construto)


async def score_overengineering(
    code: str, gateway: ModelGateway, *, tier: Tier = Tier.JUDGE
) -> Result[JudgeScore, Error]:
    """Nota de over-engineering do código. Erro se o juiz não seguir a rubrica (nota/construto)."""
    res = await gateway.complete(
        [
            ChatMessage(role="system", content=JUDGE_SYSTEM),
            ChatMessage(role="user", content=code),
        ],
        tier,
    )
    if isinstance(res, Err):
        return res
    parsed = _parse(res.value.text)
    if parsed is None:
        return Err(Error("bench", "juiz não seguiu a rubrica (nota/construto ausente)"))
    return Ok(parsed)


async def selftest(gateway: ModelGateway, *, tier: Tier = Tier.JUDGE) -> Result[bool, Error]:
    """O juiz é confiável? Pontua a ref OVER acima da MIN? Roda ANTES de pontuar de verdade."""
    over = await score_overengineering(_SELFTEST_OVER, gateway, tier=tier)
    if isinstance(over, Err):
        return over
    mini = await score_overengineering(_SELFTEST_MIN, gateway, tier=tier)
    if isinstance(mini, Err):
        return mini
    return Ok(over.value.nota > mini.value.nota)


async def trusted_score(
    code: str, gateway: ModelGateway, *, tier: Tier = Tier.JUDGE
) -> Result[JudgeScore, Error]:
    """Pontua SÓ se o juiz passar no self-test antes (senão o veredito é inútil — não pontua)."""
    st = await selftest(gateway, tier=tier)
    if isinstance(st, Err):
        return st
    if not st.value:
        return Err(Error("bench", "juiz reprovou o self-test (não discrimina over-eng)"))
    return await score_overengineering(code, gateway, tier=tier)
