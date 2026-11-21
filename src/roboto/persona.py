"""Âncora de PAPEL (persona) para refino/impl — LIGADA por default (ajustável por flag).

Hipótese (medida no PoC #245, A/B 2026-11-07): em modelo LOCAL mais fraco (qwen/GLM), uma linha
curta e ESPECÍFICA de papel ajuda a adotar a ALTITUDE certa — tech lead que define escopo e cita
fontes no refino vs. engenheiro sênior que corta escopo no impl. Validada → agora é DEFAULT ON.
Determinismo: é só uma string prefixada no prompt; desligável por flag p/ voltar ao baseline.

Flag (env `REFINE_PERSONA` / `IMPL_PERSONA`):
- ausente / vazio / "1" / "on"  → usa a âncora DEFAULT abaixo (ligada — comportamento padrão).
- "0" / "off" / "false" / "no"   → SEM âncora (baseline, p/ comparar).
- qualquer outro texto           → usa esse texto como âncora (override custom).
"""

from __future__ import annotations

# Instrução em INGLÊS (melhor instruction-following + menos token, sobretudo em modelo fraco); a
# SAÍDA pro humano fica em PORTUGUÊS (o time lê). Ver [[ponytail-adocao]].
REFINE_PERSONA_DEFAULT = (
    "You act as an experienced TECH LEAD refining the backlog: GROUND the proposal in the repo AND "
    "the provided research sources (don't write in the abstract — cite real files/symbols AND the "
    "source URLs), decide WHAT and the CRITERIA weighing scope and risk, and do NOT implement. "
    "Write every human-facing text (issue body, comments) in PORTUGUESE."
)

IMPL_PERSONA_DEFAULT = (
    "You act as a SENIOR SOFTWARE ENGINEER: before coding, learn the repo's STACK and CONVENTIONS "
    "(front-end or back-end) and FOLLOW the existing patterns; deliver only what the issue asks, "
    "with a test, minimal scope, and care for what could break (regressions). Write every "
    "human-facing text (PR, comments, commit message) in PORTUGUESE."
)

_OFF = frozenset({"0", "off", "false", "no"})
_ON = frozenset({"", "1", "on", "true", "yes"})


def resolve_persona(raw: str, default: str) -> str:
    """Resolve a flag na linha de âncora efetiva. Default LIGADO. Ver docstring do módulo."""
    valor = raw.strip()
    if valor.lower() in _OFF:
        return ""  # explicitamente desligada (baseline)
    if valor.lower() in _ON:
        return default  # ausente/"1"/"on" → âncora default (ligada)
    return valor  # texto custom


def anchor_line(persona: str) -> str:
    """Prefixo pronto p/ colar no topo do prompt (com quebra dupla), ou '' se desligado."""
    return f"{persona}\n\n" if persona else ""
