"""Entrypoint do daemon (D3): liga config -> store -> adapters -> servidor ASGI + laços.

Glue fino (não coberto por tier-1: exige Postgres + uvicorn + credenciais). A lógica de cada peça é
testada isoladamente; aqui só as orquestramos em execução contínua. Rode com `python -m roboto`.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from roboto.app.compose import build_adapters
from roboto.app.loops import poll_tick, run_periodic
from roboto.config import load_config
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
        )

    import uvicorn  # import tardio: só o daemon precisa

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info"))
    try:
        await asyncio.gather(
            server.serve(),
            run_periodic(_poll, 2.0, stop),
            run_periodic(lambda: publish_outbox(store, adapters.router, _now()), 1.0, stop),
            run_periodic(lambda: sweep(store, _now()), 30.0, stop),
        )
    finally:
        await store.close()
    return 0
