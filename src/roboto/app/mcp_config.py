"""Montagem determinística dos MCP servers por agente (F/H).

O `code-intel` (navegação semântica verificada = menos token, F) vale para TODOS os agentes.
A **busca web** (Tavily) é **exclusiva do refino** (least-privilege, H): quem implementa não
navega a internet; quem **refina/define** a issue, sim — para fundamentar com fontes externas
quando o texto e o repo não bastam (ver #203). Por que MCP e não `WebSearch` nativo: os modelos
vão via ccr→OpenRouter, e `WebSearch` é tool server-side da Anthropic — não funciona fora da API
dela. Esta função é **pura** (sem I/O): o glue (`runtime`) só a chama; o teste cobre o roteamento.
"""

from __future__ import annotations

_CODE_INTEL: dict[str, object] = {"command": "code-intel-mcp"}


def build_mcp_servers(
    *, code_intel: bool, tavily_key: str = "", web: bool = False
) -> dict[str, object] | None:
    """MCP servers do agente. `web=True` + `tavily_key` → adiciona o Tavily (busca web).

    Sem key, `web` é ignorado silenciosamente (degrada para "sem busca", não quebra o refino).
    Retorna `None` quando nenhum server se aplica (o SDK trata como "sem MCP").
    """
    servers: dict[str, object] = {}
    if code_intel:
        servers["code-intel"] = dict(_CODE_INTEL)
    if web and tavily_key:
        # `tavily-mcp` é pré-instalado global na imagem (Dockerfile) → npx usa o local, sem baixar
        # em runtime (determinismo: não depende de rede no 1º uso do refino).
        servers["tavily"] = {
            "command": "npx",
            "args": ["-y", "tavily-mcp"],
            "env": {"TAVILY_API_KEY": tavily_key},
        }
    return servers or None
