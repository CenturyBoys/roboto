"""Injeção HARNESS-DRIVEN do contexto de issues RELACIONADAS (determinismo primeiro).

O refino/impl recebe só o corpo da issue ATUAL; referências como "Depende de #244" ou
"Parte do épico #67" entram no prompt como TEXTO, sem o conteúdo delas. O modelo local não vai
buscar sozinho (mesma lição do `web_research`/`code-intel`: #203). E no refino nem há como — ele é
read-only (sem Bash). Então o HARNESS resolve os `#N`, LÊ cada issue e INJETA um bloco de contexto.

Princípio: **consultar (ler) ≠ mexer (editar)**. O harness só LÊ as relacionadas e injeta; o refino
segue sem ferramenta de mutação — o least-privilege (tool_policy) continua intacto.

I/O injetável (`fetch_issue` = a porta `github.get_issue`) → testável em tier-1.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from roboto.orchestrator.model import Error
from roboto.result import Ok, Result

# fetch_issue(repo, number) -> Result[(título, corpo)] — a porta github.get_issue, injetada.
FetchIssue = Callable[[str, int], Awaitable[Result[tuple[str, str], Error]]]

_ISSUE_REF = re.compile(r"#(\d+)")


def extract_issue_refs(body: str, *, self_id: int | None = None) -> list[int]:
    """Números `#N` citados no corpo, na ordem de aparição, sem repetir e sem a própria issue."""
    vistos: set[int] = set()
    refs: list[int] = []
    for match in _ISSUE_REF.finditer(body):
        numero = int(match.group(1))
        if numero == self_id or numero in vistos:
            continue
        vistos.add(numero)
        refs.append(numero)
    return refs


def _digest(body: str, limite: int = 600) -> str:
    """Resumo de uma linha do corpo (colapsa espaços), truncado — contexto, não a issue inteira."""
    texto = " ".join(body.split())
    return texto[:limite] + ("…" if len(texto) > limite else "")


async def related_issues_block(
    repo: str,
    body: str,
    fetch_issue: FetchIssue,
    *,
    self_id: int | None = None,
    max_issues: int = 5,
) -> str:
    """Resolve os `#N` do corpo → lê cada issue → bloco markdown '## Issues relacionadas'.

    Vazio se não há referências ou nenhuma pôde ser lida. Degrada (nunca bloqueia o refino): uma
    issue que falha ao carregar é simplesmente pulada.
    """
    refs = extract_issue_refs(body, self_id=self_id)[:max_issues]
    if not refs:
        return ""
    trechos: list[str] = []
    for numero in refs:
        got = await fetch_issue(repo, numero)
        if not isinstance(got, Ok):
            continue  # issue inacessível: pula (degrada, não quebra)
        titulo, corpo = got.value
        trechos.append(f"### #{numero} · {titulo}\n{_digest(corpo)}")
    if not trechos:
        return ""
    header = "## Issues relacionadas (CONTEXTO — leia para fundamentar; NÃO edite estas issues)"
    return header + "\n" + "\n\n".join(trechos)
