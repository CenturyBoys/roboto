"""Classificador determinístico de complexidade de tarefa -> tier de modelo do impl (F/D7).

Decisão de MODELO do motor por CLASSE de tarefa, sem LLM (determinismo primeiro): tarefa
pequena/mecânica roda no motor barato (qwen); tarefa grande/arquitetural sobe para o motor forte
(Sonnet). Lê sinais objetivos da issue — nº de arquivos citados e vocabulário arquitetural — não
"acha" nada. O id do modelo forte é política do chamador (ver ROBOTO_STRONG_MODEL no pr_cycle).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from roboto.llm.decide import Decider
from roboto.result import Err

# vocabulário que denuncia escopo arquitetural/amplo (não um ajuste pontual).
_PALAVRAS_ARQUITETURAIS = (
    "adr",
    "ports/adapters",
    "ports e adapters",
    "arquitet",
    "refator",
    "abstra",
    "migra",
    "épico",
    "epico",
    "breaking change",
)
# caminhos de arquivo citados no corpo — proxy do nº de arquivos que a tarefa toca.
_CAMINHO_DE_ARQUIVO = re.compile(
    r"[\w./@-]+\.(?:tsx?|jsx?|mjs|cjs|py|go|rs|java|rb|css|scss|sql|ya?ml)\b"
)
# >= este nº de arquivos citados = tarefa grande (tier forte UPFRONT). Subido de 3→6 (#242): o
# degrau de escalonamento já cobre o resgate, então o forte UPFRONT fica só p/ tarefa realmente
# grande — evita Sonnet na task toda por 3 arquivos (exec #88: 315k tokens). ROBOTO_TIER_FILES.
_ARQUIVOS_PARA_SER_GRANDE = int(os.environ.get("ROBOTO_TIER_FILES", "6") or "6")
_CORPO_MINIMO_PARA_ARQUITETURAL = 400  # keyword solta em corpo curto não basta


@dataclass(frozen=True)
class TierDecision:
    """Resultado do classificador: se vai pro tier forte e por quê (pra logar)."""

    forte: bool
    motivo: str


def classificar_tier(titulo: str, corpo: str) -> TierDecision:
    """True (tier forte) para tarefa grande/arquitetural; False para pequena/mecânica."""
    texto = f"{titulo}\n{corpo}".lower()
    arquivos_citados = {m.group(0) for m in _CAMINHO_DE_ARQUIVO.finditer(corpo or "")}
    palavras_encontradas = [p for p in _PALAVRAS_ARQUITETURAIS if p in texto]

    if len(arquivos_citados) >= _ARQUIVOS_PARA_SER_GRANDE:
        n = len(arquivos_citados)
        return TierDecision(True, f"{n} arquivos citados (limiar {_ARQUIVOS_PARA_SER_GRANDE})")
    if palavras_encontradas and len(corpo or "") > _CORPO_MINIMO_PARA_ARQUITETURAL:
        return TierDecision(True, f"arquitetural {palavras_encontradas[:3]} + corpo extenso")
    return TierDecision(False, "escopo pequeno/mecânico")


_TIER_QUESTION = (
    "Esta issue de engenharia exige um modelo de coding FORTE (caro) para ser implementada bem, "
    "em vez de um modelo barato? Dê True só para tarefa realmente ampla/arquitetural/arriscada "
    "(refator cross-módulo, design novo, mudança que quebra contrato). Ajuste pontual, bugfix "
    "localizado, CRUD, copy, config ou tarefa mecânica NÃO exigem o forte."
)


async def precisa_forte(
    titulo: str,
    corpo: str,
    *,
    decider: Decider | None = None,
    min_confidence: float = 0.6,
) -> TierDecision:
    """Degrau-2 (Jev) sobre o tier: o determinístico (`classificar_tier`) é o degrau-1.

    SEM `decider`: devolve a decisão determinística pura (fallback barato, igual hoje).
    COM `decider` (Jev): o determinístico decide PRIMEIRO; se ele JÁ mandou pro forte, respeita
    (não rebaixa — o keyword é sinal forte). Se ele disse base, o Jev tem a chance de PROMOVER uma
    issue que o keyword não pegou (escopo amplo sem citar arquivos/palavra). Só promove com
    confiança ≥ limiar. Jev falhou → cai no determinístico. Degrada, nunca bloqueia (determinismo
    1º — [[determinismo-primeiro]])."""
    base = classificar_tier(titulo, corpo)
    if decider is None or base.forte:
        return base  # sem Jev, ou o determinístico já mandou pro forte → respeita
    verdict = await decider.decide(_TIER_QUESTION, f"Título: {titulo}\n\n{corpo}")
    if isinstance(verdict, Err):
        return base  # Jev falhou → determinístico (não bloqueia)
    d = verdict.value
    if d.decision and d.confidence >= min_confidence:
        return TierDecision(True, f"jev promoveu (conf {d.confidence:.2f}): {d.reason[:80]}")
    return base
