"""Gate de prontidão da issue (DoR) — review determinístico ANTES do dev (D28, trilhas A/D).

Tier 1, sem LLM: a issue tem as seções obrigatórias e ao menos um critério de aceite verificável?
Pega o incompleto cedo (ex.: o PoC gerou uma issue sem os itens certos). O juiz semântico (LLM
barato / Jev) é a camada seguinte da escada (I) e entra junto do review de PR.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from roboto.agents.refiner import IssueDraft

_REQUIRED_SECTIONS = ("Contexto", "Escopo", "Critérios de aceite", "DoD")


@dataclass(frozen=True)
class ReadinessVerdict:
    ready: bool
    missing: list[str] = field(default_factory=list)


def check_issue_readiness(draft: IssueDraft) -> ReadinessVerdict:
    """Checagem estrutural do DoR. ``ready`` só quando nada falta."""
    missing: list[str] = []
    if not draft.title.strip():
        missing.append("título")
    body = draft.body.lower()
    for section in _REQUIRED_SECTIONS:
        if section.lower() not in body:
            missing.append(f"seção '{section}'")
    if "- [ ]" not in draft.body:
        missing.append("critério de aceite (nenhum item '- [ ]')")
    return ReadinessVerdict(ready=not missing, missing=missing)
