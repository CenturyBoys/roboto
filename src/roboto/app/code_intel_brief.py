"""Brief do code-intel pro prompt (trilha F): puxa do PRÓPRIO MCP server o catálogo de tools
(`tools/list`, auto-mantido) + um mapa do repo (`repo_map`) e injeta no prompt de implementação.

Motivação (medido): o motor ignora a regra de navegação e cai em Bash/Read (191×/51× num run vs 4×
code-intel). Pedir no prompt não força (o modelo é fraco em escolher ferramenta). Em vez de brigar,
o harness **reduz a necessidade** de navegar às cegas: entrega a lista de ferramentas semânticas
(da fonte da verdade, o server) + um mapa inicial. Determinístico e best-effort — server mudo → "".
"""

from __future__ import annotations

from roboto.app.verify import _McpClient

# tools de maior alavanca pro nosso fluxo (navegação + edição semântica + validação). Serve só p/
# ORDENAR/destacar o catálogo que vem do server — não hardcode do catálogo (esse vem de tools/list).
_PRIORITARIAS = (
    "find_symbol", "find_references", "document_symbols", "repo_map", "blast_radius",
    "rename_symbol", "replace_symbol_body", "move_symbol", "extract_function",
    "safe_apply", "simulate_edit", "safe_delete",
)
_MAX_REPO_MAP = 1500  # cap de chars do mapa (economia de token: é orientação, não dump)


def format_brief(tools: list[tuple[str, str]], repo_map: str = "") -> str:
    """Monta o bloco (pura, testável). Vazio se não há tools."""
    if not tools:
        return ""
    ordem = {n: i for i, n in enumerate(_PRIORITARIAS)}
    tools_ord = sorted(tools, key=lambda t: (ordem.get(t[0], 999), t[0]))
    linhas = [f"- {n}: {d}" if d else f"- {n}" for n, d in tools_ord]
    partes = [
        "FERRAMENTAS code-intel (MCP) DISPONÍVEIS — catálogo do próprio server. Para DESCOBRIR "
        "(onde está um símbolo, quem usa, o que quebra) e EDITAR símbolos (renomear/mover), "
        "USE estas em vez de grep/sed/Read de arquivo inteiro: é mais barato (trilha F) e a edição "
        "é correta por LSP (não corrompe string/comentário).",
        "\n".join(linhas),
    ]
    rm = (repo_map or "").strip()
    if rm:
        if len(rm) > _MAX_REPO_MAP:
            rm = rm[:_MAX_REPO_MAP] + "\n…(truncado — use repo_map/document_symbols p/ detalhar)"
        partes.append(f"MAPA INICIAL DO REPO (code-intel repo_map):\n{rm}")
    return "\n\n".join(partes)


def code_intel_brief(project: str, *, cmd: str = "code-intel-mcp", timeout: float = 20.0) -> str:
    """Puxa catálogo + repo_map do MCP server e devolve o bloco. SÍNCRONO (use asyncio.to_thread).
    Best-effort: qualquer falha/handshake mudo → "" (nunca derruba o ciclo)."""
    cli = None
    try:
        cli = _McpClient(cmd, project)
        if not cli.handshake(timeout=min(timeout, 15.0)):
            return ""
        tools = cli.list_tools(timeout)
        if not tools:
            return ""
        repo_map = ""
        try:
            repo_map = cli.call_text("repo_map", {"project": project}, timeout)
        except Exception:  # noqa: BLE001 — repo_map é opcional; o catálogo já vale sozinho
            repo_map = ""
        return format_brief(tools, repo_map)
    except Exception:  # noqa: BLE001 — best-effort: server indisponível não derruba o ciclo
        return ""
    finally:
        if cli is not None:
            cli.close()
