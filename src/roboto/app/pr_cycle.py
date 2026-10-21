"""Amarração do ciclo issue→dev→PR→review→correção no fluxo real (D28 + máquina de estados).

Liga as peças: o **motor** edita o repo → **git** (branch/commit/push) → **PR** no GitHub →
**review(≠autor)** sobre o diff → **comentário** → se reprovado, re-implementa com o feedback
(`correction_cycle`). `git`/`github` são portas (fakes no teste; `SubprocessGit`/`GithubAppClient`
no real). Aprovação NÃO mergeia — gate humano (D7).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import PullRequest, ReviewVerdict, check_issue_readiness, review_pr
from roboto.app.correction import CycleResult, correction_cycle
from roboto.engines.port import CodingEngine, EngineEventKind, RunSpec
from roboto.github.app import IssueRef
from roboto.llm.port import ModelGateway
from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result

_COST_PER_MTOK = 0.4  # custo aprox. Qwen/OpenRouter ($/milhão de tokens) — medir/afinar (L)


class GitOps(Protocol):
    async def prepare_branch(self, name: str) -> None: ...
    async def commit_all(self, message: str) -> None: ...
    async def push(self, name: str) -> None: ...


class GithubPrOps(Protocol):
    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]: ...

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]: ...

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main"
    ) -> Result[IssueRef, Error]: ...

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]: ...

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]: ...


async def run_pr_cycle(
    *,
    engine: CodingEngine,
    gateway: ModelGateway,
    github: GithubPrOps,
    git: GitOps,
    run: Run,
    workdir: str,
    reviewer: str,
    base: str = "main",
    max_attempts: int = 3,
    store: Store | None = None,
    now: datetime | None = None,
) -> CycleResult:
    branch = f"roboto/run-{run.id}"
    title = f"run {run.id}: {run.issue_id}"
    base_prompt = (
        f"Implemente a issue {run.issue_id} no repo {run.repo} (cwd {workdir}). "
        "Siga TODAS as regras do AGENTS.md — inclusive doc-in-sync (§5): mudança de regra/domínio "
        "exige atualizar a doc (.md/docs/ADR) no MESMO commit. "
        "Rode os checks do repo (lint, typecheck, testes, doc-sync) e corrija até passarem "
        "ANTES de concluir. "
        "Economia de token (F): use code-intel (símbolos/refs/rename) e ripgrep (texto literal) "
        "em vez de ler arquivos inteiros."
    )
    state: dict[str, int] = {}  # guarda o número do PR entre tentativas

    async def implement(feedback: list[str]) -> PullRequest:
        prompt = base_prompt
        if feedback:
            prompt += "\nCorrija os pontos do review:\n- " + "\n- ".join(feedback)
        spec = RunSpec(tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt)
        started = await engine.start(spec)
        tin = tout = 0
        async for event in engine.events():  # deixa o motor editar o repo
            if event.kind is EngineEventKind.FINISHED:
                tin, tout = event.tokens_in, event.tokens_out
        if store is not None and now is not None:
            # sessão do motor (D23): registra a sessão + o id NATIVO do Claude Code (p/ resume)
            session = await store.create_session(run.tenant, run.id, engine.engine, now)
            native = getattr(engine, "session_id", "") or (
                started.value if isinstance(started, Ok) else ""
            )
            if native:
                await store.set_native_session(session.id, native, now)
            # medição de token (D10/L): uso real do motor
            await store.record_llm_call(
                tenant=run.tenant,
                run_id=run.id,
                provider="openrouter",
                model="qwen/qwen3-coder",
                tier="frontier",
                tokens_in=tin,
                tokens_out=tout,
                cost_usd=(tin + tout) / 1_000_000 * _COST_PER_MTOK,
                now=now,
            )
        await git.prepare_branch(branch)
        await git.commit_all(title if not feedback else f"{title} (correção)")
        await git.push(branch)
        if "pr" not in state:
            # idempotência contra PR vivo: reaproveita o PR aberto do branch, se houver
            existing = await github.find_open_pr(run.repo, branch)
            if isinstance(existing, Ok) and existing.value is not None:
                state["pr"] = existing.value
            else:
                opened = await github.open_pr(
                    run.repo, title=title, body="PR automático do fleet.", head=branch, base=base
                )
                state["pr"] = opened.value.number if isinstance(opened, Ok) else 0
        number = state["pr"]
        diff = await github.get_pr_diff(run.repo, number)
        diff_text = diff.value if isinstance(diff, Ok) else ""
        return PullRequest(number=number, author=str(engine.engine), title=title, diff=diff_text)

    review_gw: ModelGateway = gateway
    if store is not None and now is not None:  # mede também o review (JUDGE) no llm_call
        from roboto.app.metering import MeteredGateway

        review_gw = MeteredGateway(gateway, store, tenant=run.tenant, run_id=run.id, now=now)

    async def review(pr: PullRequest) -> ReviewVerdict:
        verdict = await review_pr(pr, review_gw, reviewer=reviewer)
        value = (
            verdict.value
            if isinstance(verdict, Ok)
            else ReviewVerdict(approved=False, issues=["falha ao revisar"])
        )
        if value.approved:
            comment = "✅ Review aprovado."
        else:
            comment = "🔁 Review pediu correções:\n- " + "\n- ".join(value.issues)
        await github.comment_pr(run.repo, pr.number, comment)
        return value

    return await correction_cycle(implement=implement, review=review, max_attempts=max_attempts)


async def process_pr_run_tick(
    engine: CodingEngine,
    gateway: ModelGateway,
    github: GithubPrOps,
    store: Store,
    *,
    tenant: str,
    workdir_root: str,
    reviewer: str,
    git_factory: Callable[[str], GitOps],
    now: Callable[[], datetime],
    base: str = "main",
    lease_seconds: int = 3600,  # ciclo é longo; lease generoso p/ o sweeper não reclamar no meio
) -> None:
    """Pega o próximo run da fila e roda o ciclo. Aprovado -> VERIFYING; desistiu -> FAILED.

    Recuperável (não se perde): run keyed no banco; em restart, lease expira -> sweeper re-enfileira
    -> reprocessa (branch força-push, PR reaproveitado via find_open_pr). Merge = gate humano (D7).
    """
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds)
    if run is None:
        return

    # gate de prontidão ANTES de implementar: issue esqueleto -> pede ao humano, NÃO chuta (D28)
    if run.issue_id.isdigit():
        issue = await github.get_issue(run.repo, int(run.issue_id))
        if isinstance(issue, Ok):
            title, body = issue.value
            verdict = check_issue_readiness(IssueDraft(title=title, body=body))
            if not verdict.ready:
                falta = ", ".join(verdict.missing)
                msg = f"Issue incompleta para dev — falta: {falta}. Complete e eu sigo."
                await github.comment_pr(run.repo, int(run.issue_id), msg)
                if run.origin_chat_id:  # eco no Telegram de quem pediu (D30)
                    await store.enqueue_effect(
                        run.tenant, run.id, "telegram_notify",
                        {"chat_id": run.origin_chat_id,
                         "text": f"⚡ #{run.issue_id}: falta {falta}. Complete a issue e eu sigo."},
                        f"dor-wait:{run.id}", moment,
                    )
                await store.set_state(run.id, RunState.WAITING, moment)
                return

    workdir = f"{workdir_root}/{run.repo}"
    result = await run_pr_cycle(
        engine=engine,
        gateway=gateway,
        github=github,
        git=git_factory(workdir),
        run=run,
        workdir=workdir,
        reviewer=reviewer,
        base=base,
        store=store,  # medição de token (llm_call)
        now=moment,
    )
    await store.set_state(
        run.id, RunState.VERIFYING if result.approved else RunState.FAILED, moment
    )
    if run.origin_chat_id:  # status final volta pro Telegram de quem pediu (D30)
        pr = result.pr
        ref = f" (PR #{pr.number})" if pr is not None else ""
        txt = (
            f"✅ #{run.issue_id}: implementei e o review aprovou{ref}. Falta o merge humano."
            if result.approved
            else f"⚠️ #{run.issue_id}: não aprovei após {result.attempts} tentativa(s){ref}."
        )
        await store.enqueue_effect(
            run.tenant, run.id, "telegram_notify",
            {"chat_id": run.origin_chat_id, "text": txt}, f"done:{run.id}", moment,
        )
