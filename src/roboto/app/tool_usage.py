"""Telemetria de ferramentas por execução (Trilha F — economia de token).

Já persistimos cada chamada de ferramenta do motor como `session_event` (kind `tool_call`, com o
nome da tool). Este módulo **agrega** esses nomes num sinal COMPORTAMENTAL determinístico: o motor
está navegando pelo caminho barato (code-intel, semântico) ou lendo arquivo inteiro (`Read`, caro)?

O *custo* (tokens/US$) já é medido em `llm_call`. Aqui medimos o **comportamento** que explica o
custo — pra responder "o motor é econômico?" sem fé, e alimentar o modelo de custo (Trilha L).

Puro e sem I/O: recebe um `dict[tool_name, contagem]` (o store faz o GROUP BY) e devolve o resumo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Categorias, em ordem estável de exibição. `semantic` = caminho barato (code-intel); `read_full` =
# ler arquivo inteiro (caro — o que a ferramentificação quer evitar).
CATEGORIES = ("semantic", "read_full", "search", "edit", "shell", "other")

# tools built-in do Claude Code por categoria (nome exato que o SDK emite em `block.name`).
_READ_FULL = {"Read"}
_SEARCH = {"Grep", "Glob"}
_EDIT = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
_SHELL = {"Bash", "BashOutput", "KillShell"}


def categorize_tool(name: str) -> str:
    """Mapeia o nome de uma ferramenta para uma categoria de `CATEGORIES`.

    code-intel (MCP) vem como `mcp__code-intel__<tool>` → **semantic** (inclui navegação E edição
    verificada, que são o caminho barato que queremos). O resto cai nos built-ins do Claude Code.
    """
    if name.startswith("mcp__code-intel__") or name.startswith("mcp__code_intel__"):
        return "semantic"
    if name in _READ_FULL:
        return "read_full"
    if name in _SEARCH:
        return "search"
    if name in _EDIT:
        return "edit"
    if name in _SHELL:
        return "shell"
    return "other"


@dataclass(frozen=True)
class ToolUsage:
    """Resumo do uso de ferramentas de uma execução."""

    total: int
    by_category: dict[str, int] = field(default_factory=dict)
    # eficiência de navegação: entre as ops de "olhar código" (semantic + read_full), a fração que
    # foi pelo caminho barato (semantic). 1.0 = sempre semântico (ideal); 0.0 = sempre arquivo
    # inteiro (desperdício). `None` quando não houve nenhuma op de navegação (não dá pra opinar).
    efficiency: float | None = None


def summarize(counts: dict[str, int]) -> ToolUsage:
    """Agrega contagens por nome de ferramenta num `ToolUsage` (categorias + eficiência)."""
    by_category = dict.fromkeys(CATEGORIES, 0)
    for name, n in counts.items():
        by_category[categorize_tool(name)] += int(n)
    total = sum(by_category.values())
    nav = by_category["semantic"] + by_category["read_full"]
    efficiency = (by_category["semantic"] / nav) if nav else None
    return ToolUsage(total=total, by_category=by_category, efficiency=efficiency)
