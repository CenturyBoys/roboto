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

REFINE_PERSONA_DEFAULT = (
    "Você atua como um TECH LEAD experiente refinando o backlog: FUNDAMENTA a proposta no repo E "
    "nas fontes de pesquisa fornecidas (não escreva no abstrato — cite arquivos/símbolos reais E "
    "as URLs das fontes), decide O QUÊ e os CRITÉRIOS pensando em escopo e risco, e NÃO implementa."
)

IMPL_PERSONA_DEFAULT = (
    "Você atua como um ENGENHEIRO DE SOFTWARE SÊNIOR: antes de codar, entende o STACK e as "
    "CONVENÇÕES do repo (seja front-end ou back-end) e SEGUE os padrões já existentes; entrega só "
    "o que a issue pede, com teste, escopo mínimo e cuidado com o que pode quebrar (regressões)."
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
