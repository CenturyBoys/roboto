"""Porta de DECISÃO estruturada — degrau-2 da escada de validação (trilha I).

Interface onde o determinístico (degrau-1) não basta e um frontier (degrau-3) é caro: devolve um
veredito TIPADO com **confiança calibrada**. `Jev` (System One) é a implementação alvo
(`llm/jev.py`), mas é **plugável** — um judge barato ou um stub servem de fallback. Quem consome
(ex.: gate de pesquisa do refino) NUNCA casa com um vendor: depende só desta porta, com fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from roboto.orchestrator.model import Error
from roboto.result import Result


@dataclass(frozen=True)
class Decision:
    """Veredito de uma decisão sim/não + confiança calibrada (0..1) + motivo legível."""

    decision: bool
    confidence: float
    reason: str = ""


class Decider(Protocol):
    async def decide(self, question: str, context: str) -> Result[Decision, Error]: ...
