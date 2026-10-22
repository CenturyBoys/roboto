"""Entrypoint do daemon (D3): liga config -> store -> adapters -> servidor ASGI + laços.

Config vive no **banco** (fonte única, trilha O). O boot **semeia** o `.env` no banco (origem env
vira registro) e lê a config efetiva de lá. Se faltar algo obrigatório, sobe em **modo setup**
(cockpit + tela de config) em vez de morrer; quando a config fica completa, recarrega e sobe os
laços. `DATABASE_URL`/`CONSOLE_TOKEN` são bootstrap: só via env.

Glue fino (não coberto por tier-1: exige Postgres + uvicorn + credenciais). A lógica de cada peça é
testada isoladamente. Rode com `python -m roboto`.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from roboto.app.compose import build_adapters
from roboto.app.loops import poll_tick, process_run_tick, run_periodic
from roboto.app.session_hub import SessionHub
from roboto.config import BOOTSTRAP_KEYS, Config, load_config, settable_from_env
from roboto.engines.stub import StubEngine
from roboto.orchestrator.core import publish_outbox, sweep
from roboto.orchestrator.pg_store import PostgresStore
from roboto.orchestrator.store import Store
from roboto.result import Err
from roboto.web.app import build_app
from roboto.web.setup import build_setup_app

_PORT = 8080


def _now() -> datetime:
    return datetime.now(UTC)


async def _run_daemon(config: Config, store: Store) -> None:
    adapters = build_adapters(config, store)  # router inclui telegram_question
    hub = SessionHub()  # sessões vivas do co-piloto (Fatia 5); o driver interativo as registra
    app = build_app(
        store, config=config, hub=hub, issue_source=adapters.github, gateway=adapters.gateway
    )
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
            engine_scope=(config.engine == "claude_code"),
        )

    import uvicorn  # import tardio: só o daemon precisa

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=_PORT, log_level="info"))
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
        from roboto.app.scope import process_scope_tick
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

        async def _run_scope() -> None:
            # motor escaneia o repo (leitura) e monta a issue -> proposta no Telegram (G/F/I)
            await process_scope_tick(
                claude, store, tenant=config.tenant, workdir_root="/work", now=_now
            )

        tasks.append(run_periodic(_run_claude, 5.0, stop))
        tasks.append(run_periodic(_run_scope, 5.0, stop))

    await asyncio.gather(*tasks)


async def _run_setup(store: Store, bootstrap: dict[str, str]) -> None:
    """Serve o cockpit em modo setup até a config ficar completa (reload_event)."""
    import uvicorn

    reload_event = asyncio.Event()
    app = build_setup_app(
        store,
        token=bootstrap.get("CONSOLE_TOKEN", ""),
        bootstrap=bootstrap,
        reload_event=reload_event,
        now=_now,
    )
    if not bootstrap.get("CONSOLE_TOKEN"):
        print("AVISO: CONSOLE_TOKEN ausente — a tela de setup não poderá salvar. Defina-o no env.")
    print(f"modo setup: abra http://<host>:{_PORT} e configure (precisa do CONSOLE_TOKEN).")
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=_PORT, log_level="info"))

    async def _watch() -> None:
        await reload_event.wait()
        server.should_exit = True  # config salva -> encerra o setup; o main recarrega

    await asyncio.gather(server.serve(), _watch())


async def main() -> int:
    env = os.environ
    database_url = env.get("DATABASE_URL")
    if not database_url:
        print("config inválida: defina DATABASE_URL (bootstrap)")
        return 1

    store = await PostgresStore.connect(database_url)
    try:
        # semeia o .env no banco (origem env vira registro; o banco é a fonte única — trilha O)
        seed = settable_from_env(env)
        if seed:
            await store.set_app_config(seed, _now())
        bootstrap = {k: env[k] for k in BOOTSTRAP_KEYS if env.get(k)}

        while True:
            stored = await store.get_app_config()
            # bootstrap (DATABASE_URL/CONSOLE_TOKEN) sobre o banco (fonte única da config)
            loaded = load_config({**stored, **bootstrap})
            if isinstance(loaded, Err):
                print(f"modo setup: {loaded.error.message}")
                await _run_setup(store, bootstrap)
                continue  # config salva pela tela -> recarrega e reavalia
            await _run_daemon(loaded.value, store)
            return 0
    finally:
        await store.close()
