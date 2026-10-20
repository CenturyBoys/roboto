"""Smoke observável da Fase 1: roda o ClaudeCodeEngine numa tarefa dentro do repo-alvo e imprime
CADA evento. Isola o risco (Claude Code via ccr/Qwen roda e mexe no repo?) — sem Postgres/Telegram.

Precisa só de: ccr no ar (ANTHROPIC_BASE_URL) + OPENROUTER_API_KEY + o checkout do repo.
Uso (dentro do container): python poc/run_engine.py "adicione util X em packages/core com teste"
"""

from __future__ import annotations

import asyncio
import os
import sys

from roboto.engines.claude_code import ClaudeCodeEngine
from roboto.engines.port import RunSpec
from roboto.result import Err


async def main() -> int:
    task = " ".join(sys.argv[1:]).strip() or "Liste a estrutura do projeto e resuma em 3 linhas."
    repo = os.environ.get("ROBOTO_DEFAULT_REPO", "repo")
    workdir = os.environ.get("TARGET_WORKDIR", f"/work/{repo}")
    print(f"[fase1] repo={repo} cwd={workdir}")
    print(f"[fase1] tarefa: {task}")

    engine = ClaudeCodeEngine(permission_mode="bypassPermissions")
    spec = RunSpec(
        tenant=os.environ.get("ROBOTO_TENANT", "poc"), repo=repo, workdir=workdir, prompt=task
    )
    started = await engine.start(spec)
    if isinstance(started, Err):
        print(f"[fase1] start FALHOU: {started.error.message}")
        return 1

    n = 0
    async for ev in engine.events():
        n += 1
        extra = f" tool={ev.tool}" if ev.tool else ""
        text = ev.text.replace("\n", " ")[:300]
        print(f"[fase1] {ev.kind}:{extra} {text}")
    print(f"[fase1] fim — {n} eventos, session_id={engine.session_id or '(nenhum)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
