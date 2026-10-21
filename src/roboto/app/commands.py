"""Comandos do operador via chat (Telegram): consultar e atribuir trabalho explicitamente.

Parsing puro e determinístico (intenção, D30/Inc 2):
- ``list``  — listar issues abertas (inclui perguntas tipo "qual issue dá pra fazer").
- ``pick``  — pegar/atribuir a issue N ao fleet (dispara o ciclo).
- ``discuss`` — falar sobre uma issue que JÁ existe (#N / "issue N"): buscar e conversar sobre ela.
- ``help`` — saudação/ajuda ("ajuda", "/start", "oi"): manda o guia de uso (sem LLM).
- ``None`` — texto sem comando = ideia NOVA (vai pro refino conversacional).
"""

from __future__ import annotations

import re

_HELP = re.compile(
    r"^/?(?:ajuda|help|comandos?|menu|start|oi+|ol[áa]|e[ai]+|bom\s+dia|boa\s+(?:tarde|noite))\b"
)
_PICK = re.compile(r"^/?(?:pegar|pega|assumir|assume|trabalh\w*)\s+#?(\d+)\b")
_LIST = re.compile(
    r"^/?(?:"
    r"issues?(?:\s+(?:abert\w*|disponiv\w*|pendent\w*))?"
    r"|lista[r]?\s+issues?"
    r"|quais?\s+issues?"
    r"|qual\s+issue"
    r"|o\s+que\s+(?:tem|d[áa]|posso|dá\s+pra)\s+(?:pra\s+)?fazer"
    r")\b"
)
# referência a issue existente: "#180" ou "issue 180" / "issue #180" (não é comando pick/list)
_ISSUE_REF = re.compile(r"(?:(?:^|\s)#(\d+)\b|\bissue\s+#?(\d+)\b)")


def parse_command(text: str) -> tuple[str, str] | None:
    """-> ('help','') | ('pick','<N>') | ('discuss','<N>') | ('list','') | None.

    Ordem importa: ``help`` > ``pick`` (pega #N) > ``discuss`` (ref a #N) > ``list`` (sem número).
    """
    t = text.strip().lower()
    if _HELP.match(t):
        return ("help", "")
    m = _PICK.match(t)
    if m:
        return ("pick", m.group(1))
    d = _ISSUE_REF.search(t)
    if d:
        return ("discuss", d.group(1) or d.group(2))
    if _LIST.match(t):
        return ("list", "")
    return None
