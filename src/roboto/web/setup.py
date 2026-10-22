"""Modo setup (trilha O): quando falta config, o daemon serve ESTE app em vez de morrer.

Serve o mesmo cockpit (que detecta `mode: "setup"` no `/healthz` e mostra a tela de configuração)
+ endpoints p/ ler o que falta e **salvar a config no banco** (fonte única). Protegido pelo
`CONSOLE_TOKEN` (bootstrap). Ao ficar completa, dispara `reload_event` → o daemon recarrega e sobe
os laços. `DATABASE_URL`/`CONSOLE_TOKEN` seguem só via env (bootstrap), nunca por aqui.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from roboto.config import SETTABLE_KEYS, config_status
from roboto.orchestrator.store import Store
from roboto.web.console import shell_routes


def setup_routes(
    store: Store,
    *,
    token: str,
    bootstrap: Mapping[str, str],
    reload_event: asyncio.Event,
    now: Callable[[], datetime],
) -> list[BaseRoute]:
    settable = set(SETTABLE_KEYS)

    def _unauthorized(request: Request) -> bool:
        return not token or request.headers.get("authorization") != f"Bearer {token}"

    async def _status() -> dict[str, object]:
        stored = await store.get_app_config()
        return config_status({**stored, **bootstrap})  # DATABASE_URL etc. vêm do bootstrap

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "mode": "setup"})  # front mostra a tela de config

    async def status(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return JSONResponse(await _status())

    async def save(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        raw = body.get("values", {}) if isinstance(body, dict) else {}
        # só chaves setáveis e valores não-vazios; DATABASE_URL/CONSOLE_TOKEN são ignorados aqui.
        values = {k: str(v) for k, v in raw.items() if k in settable and str(v).strip()}
        if values:
            await store.set_app_config(values, now())
        stored = await store.get_app_config()
        st = config_status({**stored, **bootstrap})
        if st["configured"]:
            reload_event.set()  # daemon recarrega e sobe os laços
        return JSONResponse({"saved": sorted(values), **st})

    return [
        *shell_routes(),
        Route("/healthz", healthz),
        Route("/setup/status", status),
        Route("/setup", save, methods=["POST"]),
    ]


def build_setup_app(
    store: Store,
    *,
    token: str,
    bootstrap: Mapping[str, str],
    reload_event: asyncio.Event,
    now: Callable[[], datetime],
) -> Starlette:
    return Starlette(
        routes=setup_routes(
            store, token=token, bootstrap=bootstrap, reload_event=reload_event, now=now
        )
    )
