"""Defesa anti-loopjacking para aprovação por ação (Trilha H).

Loopjacking: o atacante faz o humano aprovar uma ação enquanto o sistema executa OUTRA (troca de
estado entre o "aprovar" e o "usar"). Defesa verificada (pesquisa H): **canonical rendering** +
**comparação EXATA no uso** — o que foi aprovado tem de ser idêntico ao que executa.

Este módulo é o PRIMITIVO puro: renderiza a ação de forma canônica (determinística), gera um digest
e compara no uso. O **enforcement** (gatear a tool via callback `can_use_tool` do SDK) fica como
sliver — depende do SDK vivo (ver `engines/claude_code` TODO). Aqui já dá pra assinar e verificar.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def canonical_action(tool: str, args: dict[str, object]) -> str:
    """Renderização CANÔNICA e determinística de uma ação (tool + argumentos).

    Chaves ordenadas e separadores fixos → a MESMA ação sempre vira a MESMA string, independente da
    ordem dos argumentos. É o que o humano "aprova" e o que se recomputa no uso.
    """
    payload = json.dumps(args, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{tool.strip()}\n{payload}"


def action_digest(tool: str, args: dict[str, object]) -> str:
    """Digest estável (sha256) da ação canônica — o que se guarda ao aprovar."""
    return hashlib.sha256(canonical_action(tool, args).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovedAction:
    """Ação aprovada por um humano: a tool, os args e o digest assinado no momento da aprovação."""

    tool: str
    args: dict[str, object]
    digest: str

    @staticmethod
    def sign(tool: str, args: dict[str, object]) -> ApprovedAction:
        return ApprovedAction(tool=tool, args=args, digest=action_digest(tool, args))


def matches(approved: ApprovedAction, tool: str, args: dict[str, object]) -> bool:
    """`True` só se a ação a executar é EXATAMENTE a aprovada (comparação por digest).

    Qualquer troca (tool diferente, argumento alterado, estado mexido pós-aprovação) → `False` → o
    chamador NEGA a execução. Na dúvida, nega (não executa o que não foi aprovado)."""
    return action_digest(tool, args) == approved.digest
