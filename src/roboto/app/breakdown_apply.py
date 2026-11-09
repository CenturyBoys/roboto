"""Materializar um breakdown de épico em sub-issues no GitHub (incremento 3 da #203).

Determinístico: dada a lista de esqueletos (já confirmada pelo humano), cria as sub-issues EM
ORDEM, encadeando cada uma com ``Depende de #<número real da anterior>`` — números que só existem
APÓS criar, daí a criação sequencial. Isso pluga no gate ``app/deps.py:blocked_by`` (a dependente
fica em WAITING até a anterior fechar). Cada filha referencia o épico, e o épico recebe um
comentário-índice das filhas (épico = guarda-chuva / registro).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from roboto.agents.breakdown import Breakdown, skeleton_body
from roboto.github.app import IssueRef
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class GithubIssueOps(Protocol):
    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]: ...
    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]: ...


@dataclass(frozen=True)
class CreatedSubIssue:
    number: int
    url: str
    title: str


async def materialize_breakdown(
    github: GithubIssueOps, repo: str, epic_number: int, breakdown: Breakdown
) -> Result[list[CreatedSubIssue], Error]:
    """Cria as sub-issues do breakdown em ordem, encadeadas, e linka no épico.

    Para na 1ª falha (não deixa a cadeia pela metade sem avisar). As já criadas permanecem — o
    operador vê no comentário do épico o que entrou.
    """
    created: list[CreatedSubIssue] = []
    created_numbers: list[int] = []
    for item in breakdown.items:
        # resolve o NÚMERO real da issue da qual esta depende: dependência NOMEADA (DAG) vence o
        # encadeamento simples; ambas referenciam só itens JÁ criados (por isso a criação em ordem).
        if item.depends_on_index is not None and 0 <= item.depends_on_index < len(created_numbers):
            dep = created_numbers[item.depends_on_index]
        elif item.depends_on_prev and created_numbers:
            dep = created_numbers[-1]
        else:
            dep = None
        body = f"{skeleton_body(item, dep)}\n\nParte do épico #{epic_number}."
        res = await github.create_issue(repo, item.title, body)
        if isinstance(res, Err):
            return Err(res.error)
        ref = res.value
        created.append(CreatedSubIssue(number=ref.number, url=ref.url, title=item.title))
        created_numbers.append(ref.number)
    if created:
        linhas = "\n".join(f"- [ ] #{c.number} — {c.title}" for c in created)
        await github.comment_pr(repo, epic_number, f"Breakdown criado (sub-issues):\n{linhas}")
    return Ok(created)
