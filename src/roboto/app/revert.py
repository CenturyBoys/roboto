"""Recuperação git-first (Trilha H): reverter um PR e reabrir a issue.

Mecanismo de rollback DECIDIDO (determinístico, git-first): o operador manda **reverter** pelo
cockpit; o daemon (que tem git) cria uma branch de revert a partir da base, reverte os commits do PR
original, empurra e abre um **PR de revert** (merge continua humano) — e **reabre a issue** pra o
fleet refazer. Nada destrutivo roda direto: o revert é uma PROPOSTA (um PR).

O run de revert carrega o PR a reverter no `execution_pr` (o endpoint copia do run original), então
o processador só lê `get_execution_pr(run.id)`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from roboto.app.pr_cycle import GithubPrOps, GitOps
from roboto.orchestrator.model import RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok


async def process_revert_tick(
    github: GithubPrOps,
    store: Store,
    *,
    tenant: str,
    workdir_root: str,
    git_factory: Callable[[str], GitOps],
    now: Callable[[], datetime],
    base: str = "main",
    lease_seconds: int = 1800,
) -> None:
    """Pega o próximo run `revert` e reverte o PR ligado a ele. Sucesso -> DONE; falha -> FAILED."""
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds, agent="revert")
    if run is None:
        return

    pr = await store.get_execution_pr(run.id)
    if pr is None:
        await store.set_state(run.id, RunState.FAILED, moment)
        await store.append_session_event(
            run.tenant, run.id, "message", moment, text="revert: sem PR ligado a esta execução."
        )
        return

    head = await github.get_pr_head(run.repo, pr.number)
    source_branch = head.value if isinstance(head, Ok) else f"roboto/run-{run.id}"
    revert_branch = f"revert/run-{run.id}"
    git = git_factory(f"{workdir_root}/{run.repo}")

    ok = await git.revert_range(base, source_branch, revert_branch)
    if not ok:
        await store.set_state(run.id, RunState.FAILED, moment)
        await store.append_session_event(
            run.tenant, run.id, "message", moment,
            text=(
                f"revert do PR #{pr.number} falhou (conflito?) — nada foi empurrado. "
                "Reverta manualmente ou resolva o conflito."
            ),
        )
        return

    await git.push(revert_branch)
    title = f"revert: desfaz o PR #{pr.number}"
    body = (
        f"Revert automático do PR #{pr.number} (recuperação — Trilha H).\n\n"
        f"Reabre a issue #{run.issue_id} pra o fleet refazer. Merge continua humano."
    )
    opened = await github.open_pr(
        run.repo, title=title, body=body, head=revert_branch, base=base
    )
    revert_number = opened.value.number if isinstance(opened, Ok) else 0

    # reabre a issue (se for issue numérica) e comenta o rastro
    if run.issue_id.isdigit():
        await github.set_issue_state(run.repo, int(run.issue_id), "open")
    await github.comment_pr(
        run.repo, pr.number,
        f"↩️ Revert aberto (PR #{revert_number}) e issue #{run.issue_id} reaberta. Merge é humano.",
    )

    if revert_number:
        url = f"https://github.com/{run.repo}/pull/{revert_number}"
        await store.set_execution_pr(run.id, revert_number, url, "", moment)
    await store.set_state(run.id, RunState.DONE, moment)
    await store.append_session_event(
        run.tenant, run.id, "message", moment,
        text=f"✅ revert do PR #{pr.number} aberto como PR #{revert_number}; issue reaberta.",
    )
