"""Reconciliar runs ATIVOS órfãos contra o estado real do GitHub (sem webhook, via polling).

Local não tem webhook do GitHub: nada avisa que o PR foi mergeado/fechado nem que a issue fechou.
Sem isto um run fica preso num estado ATIVO (RUNNING/VERIFYING/WAITING) — segurando lock (tenant,
issue) e WIP — mesmo depois do trabalho ter LANDADO. Pior: se o motor MORRE (stream malformado) em
RUNNING sem reconciliar, o run fica "running" pra sempre (run-1050/1051). Este reconciliador fecha o
laço de forma DETERMINÍSTICA e com ZERO falso-positivo — age só quando o GitHub prova que acabou:

- PR **mergeado** → ``DONE`` (entregue).
- PR **fechado sem merge** → ``ABANDONED`` (rejeitado; libera o lock).
- sem PR linkado, mas a **issue do run (impl/refine) FECHOU** → ``DONE`` (o trabalho landou por
  outro caminho — ex.: o PR da T2 mergeado por fora fechou o #398; o run #1051 morreu em RUNNING
  e nunca saiu de lá).
- PR/issue ainda **aberto** → mantém o estado (ainda legitimamente ativo; não chuta por tempo —
  ``updated_at`` não reflete atividade de RUNNING, então staleness mataria run longo legítimo).

Cobre impl/refine (issue_id = issue; PR via ``execution_pr``) e correct (issue_id = nº do PR).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result

# estados ATIVOS (seguram lock/WIP). QUEUED fica de fora (ainda não começou; claim cuida dele).
_ACTIVE = (RunState.RUNNING, RunState.VERIFYING, RunState.WAITING)


class _GithubPr(Protocol):
    async def pr_merged(self, repo: str, number: int) -> Result[bool, Error]: ...
    async def get_issue_state(self, repo: str, number: int) -> Result[str, Error]: ...


def _pr_number(run: Run, pr_num: int | None) -> int | None:
    if pr_num is not None:
        return pr_num  # impl: número do PR linkado (execution_pr)
    if run.agent == "correct" and run.issue_id.isdigit():
        return int(run.issue_id)  # correct: o issue_id É o número do PR
    return None


async def _mark_done(
    store: Store, run: Run, pr_number: int | None, tenant: str, now: datetime
) -> None:
    await store.set_state(run.id, RunState.DONE, now)
    # second brain (Fatia 1): registra a DECISÃO "issue implementada/entregue" — fecha o loop do
    # ciclo (refino/impl de relacionadas injeta via recall). Dedup por ref.
    if run.issue_id.isdigit():
        txt = (
            f"Issue #{run.issue_id} implementada e mergeada no {run.repo} (PR #{pr_number})."
            if pr_number is not None
            else f"Issue #{run.issue_id} entregue/fechada no {run.repo} (reconciliada)."
        )
        await store.remember(
            tenant, txt, kind="decisão", ref=f"#{run.issue_id}", now=now, unique_by_ref=True,
        )


async def reconcile_active_runs(
    store: Store, github: _GithubPr, *, tenant: str, now: datetime, limit: int = 100
) -> int:
    """Fecha runs ATIVOS cujo trabalho já landou no GitHub (PR mergeado/fechado OU issue fechada).
    Devolve quantos foram resolvidos. Determinístico, sem chute por tempo."""
    resolved = 0
    for r in await store.list_runs(tenant, limit):
        if r.state not in _ACTIVE:
            continue
        pr = await store.get_execution_pr(r.id)
        number = _pr_number(r, pr.number if pr is not None else None)
        if number is not None:
            merged = await github.pr_merged(r.repo, number)
            if isinstance(merged, Ok) and merged.value:
                await _mark_done(store, r, number, tenant, now)
                resolved += 1
                continue
            st = await github.get_issue_state(r.repo, number)
            if isinstance(st, Ok) and st.value == "closed":  # PR fechado sem merge
                await store.set_state(r.id, RunState.ABANDONED, now)
                resolved += 1
            continue  # PR ainda aberto → mantém ativo
        # sem PR linkado: a ISSUE do run (impl/refine) já FECHOU? → o trabalho landou → DONE.
        # Conserto do zumbi RUNNING (#1051): motor morreu antes de linkar o PR, mas a issue fechou
        # (entregue por outro caminho). Sem isto o run fica "running" pra sempre.
        if r.agent in ("impl", "refine") and r.issue_id.isdigit():
            st = await github.get_issue_state(r.repo, int(r.issue_id))
            if isinstance(st, Ok) and st.value == "closed":
                await _mark_done(store, r, None, tenant, now)
                resolved += 1
    return resolved


# compat: o nome antigo seguia só VERIFYING; agora cobre todos os ativos (o caller não muda).
reconcile_verifying = reconcile_active_runs
