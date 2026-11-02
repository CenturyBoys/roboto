"""Máquina de estados da issue → labels (Trilha A, #161) — PROJEÇÃO AGNÓSTICA.

O estado canônico vive no daemon (o `RunState` do run mais recente da issue). O GitHub é um
**adapter**: projetamos esse estado como uma **label** `status:*` na issue. Trocar de plataforma
(GitLab/Jira) = trocar o adapter, sem tocar o mapeamento (que é puro e determinístico).

A projeção roda num laço periódico (polling, sem webhook): lê os runs, calcula a label desejada por
issue e só chama o adapter quando MUDA (dedup em memória por processo; re-sincroniza no restart).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result

# Projeta o RunState do run mais recente no vocabulário de status do PROJETO (mesmo das labels
# `status:*` do board): backlog → to-do → in-progress → in-review → done (+ blocked).
# (agent, estado) específicos primeiro; depois um genérico por estado (qualquer agente).
_BY_AGENT_STATE: dict[tuple[str, RunState], str] = {
    ("refine", RunState.QUEUED): "status:in-progress",
    ("refine", RunState.RUNNING): "status:in-progress",
    ("refine", RunState.DONE): "status:to-do",  # refinada → pronta p/ implementar
    ("scope", RunState.QUEUED): "status:in-progress",
    ("scope", RunState.RUNNING): "status:in-progress",
    ("scope", RunState.DONE): "status:to-do",
    ("impl", RunState.QUEUED): "status:in-progress",
    ("impl", RunState.RUNNING): "status:in-progress",
    ("impl", RunState.VERIFYING): "status:in-review",
    ("impl", RunState.DONE): "status:done",
    ("correct", RunState.QUEUED): "status:in-review",
    ("correct", RunState.RUNNING): "status:in-review",
    ("correct", RunState.VERIFYING): "status:in-review",
    ("correct", RunState.DONE): "status:done",
}
_BY_STATE: dict[RunState, str] = {
    RunState.WAITING: "status:blocked",
    RunState.FAILED: "status:blocked",
}

STATUS_PREFIX = "status:"


def issue_state_label(agent: str, state: RunState) -> str | None:
    """Label canônica p/ (agente, estado) do run mais recente da issue. None = não projeta."""
    specific = _BY_AGENT_STATE.get((agent, state))
    if specific is not None:
        return specific
    return _BY_STATE.get(state)


class IssueLabeler(Protocol):
    # troca as labels `status:*` da issue pela `label` (preserva as demais). Adapter de plataforma.
    async def set_issue_state_label(
        self, repo: str, number: int, label: str
    ) -> Result[None, Error]: ...


async def project_issue_labels_tick(
    github: IssueLabeler,
    store: Store,
    *,
    tenant: str,
    now: Callable[[], datetime],
    seen: dict[tuple[str, str], str],
) -> None:
    """Projeta o estado canônico (run mais recente por issue) como label `status:*` no GitHub."""
    latest: dict[tuple[str, str], Run] = {}
    for r in await store.list_runs(tenant, 200):
        key = (r.repo, r.issue_id)
        if key not in latest or r.id > latest[key].id:
            latest[key] = r
    for (repo, issue), run in latest.items():
        if not issue.isdigit():
            continue
        label = issue_state_label(run.agent, run.state)
        if label is None or seen.get((repo, issue)) == label:
            continue
        res = await github.set_issue_state_label(repo, int(issue), label)
        if isinstance(res, Ok):
            seen[(repo, issue)] = label
