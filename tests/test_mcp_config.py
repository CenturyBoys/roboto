"""Roteamento dos MCP servers por agente (F/H): code-intel p/ todos; busca web só no refino."""

from __future__ import annotations

from roboto.app.mcp_config import build_mcp_servers


def test_impl_so_code_intel_sem_web() -> None:
    servers = build_mcp_servers(code_intel=True)
    assert servers == {"code-intel": {"command": "code-intel-mcp", "alwaysLoad": True}}


def test_refino_com_chave_ganha_tavily() -> None:
    servers = build_mcp_servers(code_intel=True, tavily_key="tvly-xyz", web=True)
    assert servers is not None
    assert "code-intel" in servers
    tavily = servers["tavily"]
    assert isinstance(tavily, dict)
    assert tavily["command"] == "npx"
    assert tavily["args"] == ["-y", "tavily-mcp"]
    assert tavily["env"] == {"TAVILY_API_KEY": "tvly-xyz"}


def test_web_sem_chave_nao_adiciona_tavily() -> None:
    # degrada silencioso: refino sem busca, não quebra
    servers = build_mcp_servers(code_intel=True, tavily_key="", web=True)
    assert servers == {"code-intel": {"command": "code-intel-mcp", "alwaysLoad": True}}


def test_web_so_entra_quando_pedido() -> None:
    # impl (web=False) não recebe tavily mesmo com chave presente (least-privilege)
    servers = build_mcp_servers(code_intel=True, tavily_key="tvly-xyz", web=False)
    assert servers is not None
    assert "tavily" not in servers


def test_tudo_desligado_retorna_none() -> None:
    assert build_mcp_servers(code_intel=False) is None
    assert build_mcp_servers(code_intel=False, tavily_key="k", web=True) is not None
