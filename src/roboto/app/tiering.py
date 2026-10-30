"""Classificador determinístico de complexidade de tarefa -> tier de modelo do impl (F/D7).

Decisão de MODELO do motor por CLASSE de tarefa, sem LLM (determinismo primeiro): tarefa
pequena/mecânica roda no motor barato (qwen); tarefa grande/arquitetural sobe para o motor forte
(Sonnet). Lê sinais objetivos da issue — nº de arquivos citados e vocabulário arquitetural — não
"acha" nada. O id do modelo forte é política do chamador (ver ROBOTO_STRONG_MODEL no pr_cycle).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
_ARQUIVOS_PARA_SER_GRANDE = 3  # >= este nº de arquivos distintos = tarefa grande
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
