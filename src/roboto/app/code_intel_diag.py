"""Diagnostics HARNESS-DRIVEN pro loop de correção (trilha F/#226).

Aprendizado (run #46): o motor subusa o code-intel pra ENTENDER erro de build — roda `tsc` no Bash,
lê o output cru e corrige por tentativa-e-erro. Em vez de brigar, o harness roda o `validate_build`
(build REAL no disco) e injeta os erros ESTRUTURADOS no prompt de correção. Puxa do PRÓPRIO MCP
server (fonte da verdade); best-effort (server mudo / build ok → ""). Igual ao `code_intel_brief`,
mas pra ERROS em vez de navegação.
"""

from __future__ import annotations

import re

from roboto.app.verify import _McpClient

# só injeta quando há SINAL de erro — evita tratar "build ok" como diagnóstico (conservador).
_ERR_SIGNAL = re.compile(
    r"\berror\b|\berro\b|TS\d{3,}|cannot find|not assignable|expected|undefined|"
    r"has no exported|does not exist",
    re.IGNORECASE,
)
# erro de USO do próprio validate_build (ex.: "faltou 'lang' ou 'file'") — NÃO é diagnóstico de
# build; injetar isso mandou o motor caçar erro fantasma (#226 bug). Descarta.
_USAGE_ERR = re.compile(r"(faltou|missing|requer|required|obrigat).{0,24}('?lang'?|'?file'?)", re.I)
# erro de CONFIG/SETUP do code-intel (ex.: "sem comando de build p/ 'typescript' (defina
# TYPESCRIPT_CHECK_CMD)") — é o code-intel pedindo configuração ao OPERADOR, NÃO um erro no código.
# Injetar isso mandou o motor editar .env/turbo.json caçando env var fantasma (#245 runaway). A cura
# é configurar o code-intel (doctor no bootstrap, Fix B), não o modelo adivinhar. Descarta.
_CONFIG_ERR = re.compile(
    r"sem comando de build|_CHECK_CMD\b|n[ãa]o configurad|not configured|\bdoctor\b", re.I
)
_DIAG_MAX = 1800


def format_diagnostics(raw: str, *, max_chars: int = _DIAG_MAX) -> str:
    """Bloco dos diagnostics (PURA). Vazio se build ok, ruído, erro de USO ou de CONFIG."""
    raw = raw.strip()
    if not raw or _USAGE_ERR.search(raw) or _CONFIG_ERR.search(raw) or not _ERR_SIGNAL.search(raw):
        return ""
    if len(raw) > max_chars:
        raw = raw[:max_chars].rstrip() + "\n…(truncado)"
    return (
        "DIAGNÓSTICOS DO BUILD (code-intel validate_build — erros REAIS no disco). Corrija "
        "EXATAMENTE estes; não chute nem reescreva o que já está certo:\n" + raw
    )


def code_intel_diagnostics(
    project: str,
    file: str = "",
    *,
    lang: str = "",
    cmd: str = "code-intel-mcp",
    timeout: float = 30.0,
) -> str:
    """Roda `validate_build` no MCP e devolve o bloco de erros (ou "" se ok/indisponível).

    SÍNCRONO (use asyncio.to_thread). `file`/`lang` inferem a linguagem. Best-effort: handshake mudo
    ou exceção → "" (nunca derruba o ciclo)."""
    if not file and not lang:
        return ""  # sem dica de linguagem, validate_build só dá erro de uso — não chamar (#226)
    cli = None
    try:
        cli = _McpClient(cmd, project)
        if not cli.handshake(timeout=min(timeout, 15.0)):
            return ""
        args: dict[str, object] = {"project": project}
        if file:
            args["file"] = file
        elif lang:
            args["lang"] = lang
        raw = cli.call_text("validate_build", args, timeout)
        return format_diagnostics(raw)
    except Exception:  # noqa: BLE001 — best-effort: server indisponível não derruba o ciclo
        return ""
    finally:
        if cli is not None:
            cli.close()
