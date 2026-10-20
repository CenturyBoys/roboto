"""Comandos do operador via chat (Telegram): consultar e atribuir trabalho explicitamente.

Parsing puro e determinístico. Hoje: `list` (issues abertas) e `pick <N>` (pega/atribui a issue N
ao fleet, disparando o ciclo). Texto sem comando = ideia nova (vai pro refino).
"""

from __future__ import annotations

import re

_PICK = re.compile(r"^/?(?:pegar|pega|assumir|assume|trabalh\w*)\s+#?(\d+)\b")
_LIST = re.compile(r"^/?(?:issues|lista[r]?\s+issues?|issues?\s+abert\w*)\b")


def parse_command(text: str) -> tuple[str, str] | None:
    """-> ('list','') | ('pick','<N>') | None (não é comando)."""
    t = text.strip().lower()
    if _LIST.match(t):
        return ("list", "")
    m = _PICK.match(t)
    if m:
        return ("pick", m.group(1))
    return None
