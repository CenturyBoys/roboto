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


# labels que marcam "NÃO-pronta" — o sinal HUMANO/refino que o parser de `#N` não enxerga (ex.: a
# issue depende de uma fundação que nem virou issue, como T1/T2 do breakdown). Tunável por env.
DEFAULT_BLOCKED_LABELS = frozenset({"status:blocked", "blocked"})


def blocking_labels(
    labels: list[str], blocked: frozenset[str] = DEFAULT_BLOCKED_LABELS,
) -> list[str]:
    """Labels de BLOQUEIO presentes na issue (match case-insensitive). Vazio = nenhum bloqueio por
    label. Determinístico: o label é o veredito do humano/refino de que a issue não está pronta —
    captura o que o gate de dependência por `#N` não vê (run #1046: a #286 `status:blocked`)."""
    low = {s.strip().lower() for s in blocked}
    return [lab for lab in labels if lab.strip().lower() in low]
