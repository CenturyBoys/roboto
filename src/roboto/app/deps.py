"""Scheduling ciente de dependência (Trilha J): detectar "blocked by #N".

Issue que depende de (é bloqueada por) outra NÃO deve entrar em execução antes de a bloqueadora
fechar — senão o fleet coda em cima de algo que ainda não existe (ou dois agentes colidem na mesma
área). Determinístico: parseia o texto da issue (título + corpo) atrás de referências de BLOQUEIO.

Só pega linguagem de **bloqueio/dependência** ("blocked by / bloqueada por / depends on / depende
de #N") — NÃO "relaciona-se a / relates to / refs" (isso é só relacionado, não bloqueia).
"""

from __future__ import annotations

import re

# frase de bloqueio seguida de uma ou mais refs #N (ex.: "bloqueada por #79", "depends on #80, #81")
_BLOCK = re.compile(
    r"(?:blocked by|bloquead[ao]s? por|depends on|depende d[ea])\s*:?\s*((?:#\d+[\s,/e]*)+)",
    re.IGNORECASE,
)


def blocked_by(text: str) -> list[int]:
    """Números das issues que BLOQUEIAM esta (dedup, na ordem encontrada). Vazio = nada bloqueia."""
    nums: list[int] = []
    for m in _BLOCK.finditer(text or ""):
        for n in re.findall(r"#(\d+)", m.group(1)):
            if int(n) not in nums:
                nums.append(int(n))
    return nums
