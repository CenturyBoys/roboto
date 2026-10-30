"""Smoke Fase 1 — CICLO COMPLETO ao vivo: run_pr_cycle contra o repo real (abre PR de verdade).

Precisa: ccr no ar (ANTHROPIC_BASE_URL), OPENROUTER_API_KEY, GITHUB_API_TOKEN, checkout em
TARGET_WORKDIR. Motor via ccr/Qwen; review via OpenRouter/Qwen; git+GitHub reais.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from roboto.app.git_ops import SubprocessGit
from roboto.app.pr_cycle import run_pr_cycle
from roboto.engines.claude_code import ClaudeCodeEngine
from roboto.github.app import GithubAppClient
from roboto.llm.openrouter import OpenRouterGateway
from roboto.orchestrator.model import Run, RunState

_DEFAULT_TASK = (
    "adicionar a função pura isMatchPoint em packages/core/src/jokenpo/rules.ts "
    "(retorna true quando winner===null e scoreA ou scoreB === ROUNDS_TO_WIN-1), exportar em "
    "src/index.ts e cobrir com teste em src/jokenpo/rules.test.ts. NAO rode pnpm. Siga o AGENTS.md."
)


async def main() -> int:
    repo = os.environ.get("ROBOTO_DEFAULT_REPO", "arenavalendo/main")
    workdir = os.environ.get("TARGET_WORKDIR", f"/work/{repo}")
    base = os.environ.get("ROBOTO_BASE_BRANCH", "main")
    task = os.environ.get("POC_TASK") or _DEFAULT_TASK
    # POC_ISSUE=<n>: usa o NÚMERO da issue (run_pr_cycle puxa título+corpo do GitHub e põe Closes #n).
    # Sem POC_ISSUE, cai no texto livre de POC_TASK (modo smoke antigo).
    issue = os.environ.get("POC_ISSUE", "").strip()
    issue_id = issue if issue.isdigit() else task
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    run = Run(
        id=1,
        tenant=os.environ.get("ROBOTO_TENANT", "poc"),
        repo=repo,
        issue_id=issue_id,
        agent="impl",
        state=RunState.RUNNING,
        attempt=0,
        idempotency_key="live-1",
        created_at=moment,
        updated_at=moment,
    )
    engine = ClaudeCodeEngine(permission_mode="bypassPermissions")
    gateway = OpenRouterGateway(os.environ["OPENROUTER_API_KEY"])
    github = GithubAppClient(
        app_id="", private_key="", installation_id="", token=os.environ["GITHUB_API_TOKEN"]
    )
    git = SubprocessGit(workdir)
    print(f"[ciclo] repo={repo} base={base} cwd={workdir}")
    result = await run_pr_cycle(
        engine=engine, gateway=gateway, github=github, git=git, run=run,
        workdir=workdir, reviewer="review", base=base, max_attempts=2,
    )
    pr_url = f"https://github.com/{repo}/pull/{result.pr.number}" if result.pr else None
    print(
        f"[ciclo] approved={result.approved} attempts={result.attempts} "
        f"pr={pr_url} issues={result.issues}"
    )
    return 0 if result.approved else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
