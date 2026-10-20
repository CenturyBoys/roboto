"""Amarração do ciclo issue→dev→PR→review→correção no fluxo real (D28 + máquina de estados).

Liga as peças: o **motor** edita o repo → **git** (branch/commit/push) → **PR** no GitHub →
**review(≠autor)** sobre o diff → **comentário** → se reprovado, re-implementa com o feedback
(`correction_cycle`). `git`/`github` são portas (fakes no teste; `SubprocessGit`/`GithubAppClient`
no real). Aprovação NÃO mergeia — gate humano (D7).
"""

from __future__ import annotations

from typing import Protocol

from roboto.agents.review import PullRequest, ReviewVerdict, review_pr
from roboto.app.correction import CycleResult, correction_cycle
from roboto.engines.port import CodingEngine, RunSpec
from roboto.github.app import IssueRef
from roboto.llm.port import ModelGateway
from roboto.orchestrator.model import Error, Run
from roboto.result import Ok, Result


class GitOps(Protocol):
    async def prepare_branch(self, name: str) -> None: ...
    async def commit_all(self, message: str) -> None: ...
    async def push(self, name: str) -> None: ...


class GithubPrOps(Protocol):
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
) -> CycleResult:
    branch = f"roboto/run-{run.id}"
    title = f"run {run.id}: {run.issue_id}"
    base_prompt = (
        f"Implemente a issue {run.issue_id} do repo {run.repo} (cwd {workdir}). Siga o AGENTS.md."
    )
    state: dict[str, int] = {}  # guarda o número do PR entre tentativas

    async def implement(feedback: list[str]) -> PullRequest:
        prompt = base_prompt
        if feedback:
            prompt += "\nCorrija os pontos do review:\n- " + "\n- ".join(feedback)
        spec = RunSpec(tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt)
        await engine.start(spec)
        async for _event in engine.events():  # deixa o motor editar o repo
            pass
        await git.prepare_branch(branch)
        await git.commit_all(title if not feedback else f"{title} (correção)")
        await git.push(branch)
        if "pr" not in state:
            opened = await github.open_pr(
                run.repo, title=title, body="PR automático do fleet.", head=branch, base=base
            )
            state["pr"] = opened.value.number if isinstance(opened, Ok) else 0
        number = state["pr"]
        diff = await github.get_pr_diff(run.repo, number)
        diff_text = diff.value if isinstance(diff, Ok) else ""
        return PullRequest(number=number, author=str(engine.engine), title=title, diff=diff_text)

    async def review(pr: PullRequest) -> ReviewVerdict:
        verdict = await review_pr(pr, gateway, reviewer=reviewer)
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
