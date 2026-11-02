"""Least privilege de ferramentas por tipo de agente (Trilha H — segurança).

OWASP Agentic #… : dar ao agente só as ferramentas que a task dele exige, não o toolbox inteiro.
Agentes que só LEEM o repo (refino, escopo, review) não precisam **mutar** o filesystem nem rodar
shell — negar essas ferramentas fecha a brecha sem depender do prompt (determinismo primeiro).

Navegação (Read/Grep/Glob) e o code-intel (MCP, caminho barato — F) seguem liberados para todos;
só a **mutação** é negada aos read-only. Implementação/correção mutam → nada bloqueado.

Puro e sem I/O: o `runtime` passa o resultado a `ClaudeCodeEngine(disallowed_tools=...)`.
"""

from __future__ import annotations

# ferramentas que ESCREVEM no repo ou executam comando arbitrário (mutação / efeito colateral).
_MUTATION_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash")

# agentes read-only: o "done" deles é uma PROPOSTA (issue refinada, escopo, review), não editar.
_READ_ONLY_AGENTS = frozenset({"refine", "scope", "review"})


def disallowed_tools_for(agent: str) -> list[str]:
    """Ferramentas NEGADAS a este tipo de agente. Vazio = sem restrição (implementação/correção)."""
    return list(_MUTATION_TOOLS) if agent in _READ_ONLY_AGENTS else []
