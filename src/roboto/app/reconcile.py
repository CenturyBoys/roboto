"""Reconciliar runs em VERIFYING contra o estado real do PR (sem webhook, via polling).

Local não tem webhook do GitHub: nada avisa que o PR foi mergeado/fechado, então um run aprovado
fica preso em ``VERIFYING`` — e, como VERIFYING é ATIVO, segura o lock (tenant, issue) e conta no
WIP. Este reconciliador fecha o laço:

- PR **mergeado** → ``DONE`` (entregue).
- PR **fechado sem merge** → ``ABANDONED`` (rejeitado; libera o lock mesmo assim).
- PR ainda **aberto** → mantém ``VERIFYING`` (esperando o gate humano).

Acha o número do PR tanto de runs de **impl** (via ``execution_pr``) quanto de **correct** (que
carregam o número do PR no ``issue_id``) — o bug era o laço antigo só enxergar impl.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result


class _GithubPr(Protocol):
    async def pr_merged(self, repo: str, number: int) -> Result[bool, Error]: ...
    async def get_issue_state(self, repo: str, number: int) -> Result[str, Error]: ...


def _pr_number(run: Run, pr_num: int | None) -> int | None:
    if pr_num is not None:
        return pr_num  # impl: número do PR linkado (execution_pr)
    if run.agent == "correct" and run.issue_id.isdigit():
        return int(run.issue_id)  # correct: o issue_id É o número do PR
    return None


async def reconcile_verifying(
    store: Store, github: _GithubPr, *, tenant: str, now: datetime, limit: int = 100
) -> int:
    """Fecha runs VERIFYING cujo PR já foi mergeado/fechado. Devolve quantos foram resolvidos."""
    resolved = 0
    for r in await store.list_runs(tenant, limit):
        if r.state is not RunState.VERIFYING:
            continue
        pr = await store.get_execution_pr(r.id)
        number = _pr_number(r, pr.number if pr is not None else None)
        if number is None:
            continue
        merged = await github.pr_merged(r.repo, number)
        if isinstance(merged, Ok) and merged.value:
            await store.set_state(r.id, RunState.DONE, now)
            # second brain (Fatia 1): registra a DECISÃO "issue implementada e mergeada" — fecha o
            # loop do ciclo (o refino/impl de relacionadas injeta via recall). Dedup por ref.
            if r.issue_id.isdigit():
                await store.remember(
                    tenant,
                    f"Issue #{r.issue_id} implementada e mergeada no {r.repo} (PR #{number}).",
                    kind="decisão", ref=f"#{r.issue_id}", now=now, unique_by_ref=True,
                )
            resolved += 1
            continue
        # não mergeado: fechado sem merge também precisa sair do VERIFYING (senão trava o lock)
        st = await github.get_issue_state(r.repo, number)
        if isinstance(st, Ok) and st.value == "closed":
            await store.set_state(r.id, RunState.ABANDONED, now)
            resolved += 1
    return resolved
