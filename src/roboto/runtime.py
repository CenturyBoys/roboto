"""Entrypoint do daemon (D3): liga config -> store -> adapters -> servidor ASGI + laços.

Glue fino (não coberto por tier-1: exige Postgres + uvicorn + credenciais). A lógica de cada peça é
testada isoladamente; aqui só as orquestramos em execução contínua. Rode com `python -m roboto`.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from roboto.app.compose import build_adapters
from roboto.app.loops import poll_tick, process_run_tick, run_periodic
from roboto.config import load_config
from roboto.engines.stub import StubEngine
from roboto.orchestrator.core import publish_outbox, sweep
from roboto.orchestrator.pg_store import PostgresStore
from roboto.result import Err
from roboto.web.app import build_app


def _now() -> datetime:
    return datetime.now(UTC)


async def main() -> int:
    loaded = load_config(os.environ)
    if isinstance(loaded, Err):
        print(f"config inválida: {loaded.error.message}")
        return 1
    config = loaded.value

    store = await PostgresStore.connect(config.database_url)
    adapters = build_adapters(config, store)  # router inclui telegram_question
    app = build_app(store, config=config)
    stop = asyncio.Event()

    async def _poll() -> None:
        await poll_tick(
            adapters.channel,
            store,
            repo=config.default_repo,
            gateway=adapters.gateway,
            transcriber=adapters.transcriber,
            now=_now,
            github=adapters.github,  # habilita o comando "issues" (listar) no Telegram
            tenant=config.tenant,  # persiste o cursor do Telegram (não relê no restart)
        )

    import uvicorn  # import tardio: só o daemon precisa

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info"))
    tasks = [
        server.serve(),
        run_periodic(_poll, 2.0, stop),
        run_periodic(lambda: publish_outbox(store, adapters.router, _now()), 1.0, stop),
        run_periodic(lambda: sweep(store, _now()), 30.0, stop),
    ]

    # laço do motor de coding (D22/PoC N3), ligado por ROBOTO_ENGINE
    if config.engine == "stub":
        stub = StubEngine([])

        async def _run_stub() -> None:
            await process_run_tick(
                stub, store, tenant=config.tenant, chat_id=config.chat_id, now=_now
            )

        tasks.append(run_periodic(_run_stub, 5.0, stop))
    elif config.engine == "claude_code":
        from roboto.app.git_ops import SubprocessGit
        from roboto.app.pr_cycle import process_pr_run_tick
        from roboto.engines.claude_code import ClaudeCodeEngine

        # imagem roda NÃO-root -> bypassPermissions (full-auto: git/pnpm/abrir PR).
        # code-intel (ide_cc) ligado por config -> navegação semântica, menos token (F).
        mcp: dict[str, object] | None = (
            {"code-intel": {"command": "code-intel-mcp"}} if config.code_intel else None
        )
        claude = ClaudeCodeEngine(permission_mode="bypassPermissions", mcp_servers=mcp)

        async def _run_claude() -> None:
            # ciclo completo: motor->git->PR->review(≠autor)->correção. Merge = gate humano (D7).
            await process_pr_run_tick(
                claude,
                adapters.gateway,
                adapters.github,
                store,
                tenant=config.tenant,
                workdir_root="/work",
                reviewer="review",
                git_factory=lambda ws: SubprocessGit(ws),
                now=_now,
                base=config.base_branch,
            )

        tasks.append(run_periodic(_run_claude, 5.0, stop))

    try:
        await asyncio.gather(*tasks)
    finally:
        await store.close()
    return 0
