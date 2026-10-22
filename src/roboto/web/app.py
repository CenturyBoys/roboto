"""App ASGI único: console (D25) + webhook do GitHub (inbound) no mesmo processo.

Mesmo backend (store) para tudo — Telegram, console e webhook não mantêm estado próprio. O webhook
valida HMAC (D21) e faz ingest idempotente; o console usa bearer + isolamento por empresa.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from roboto.app.session_hub import SessionHub
from roboto.config import Config
from roboto.github.webhook import handle_webhook
from roboto.orchestrator.store import Store
from roboto.result import Err
from roboto.web.console import IssueSource, console_routes


def _now_utc() -> datetime:
    return datetime.now(UTC)


def build_app(
    store: Store,
    *,
    config: Config,
    now: Callable[[], datetime] = _now_utc,
    hub: SessionHub | None = None,
    issue_source: IssueSource | None = None,
) -> Starlette:
    async def webhook(request: Request) -> JSONResponse:
        body = await request.body()
        result = await handle_webhook(
            secret=config.github.webhook_secret,
            tenant=config.tenant,
            event_type=request.headers.get("x-github-event", ""),
            signature=request.headers.get("x-hub-signature-256", ""),
            body=body,
            store=store,
            now=now(),
            repos=config.repos,
            trigger_label=config.trigger_label,
            bot_login=config.bot_login,
        )
        if isinstance(result, Err):
            status = 401 if result.error.kind == "invalid_signature" else 400
            return JSONResponse({"error": result.error.message}, status_code=status)
        run = result.value
        return JSONResponse(
            {"accepted": True, "run_id": run.id if run is not None else None}, status_code=202
        )

    routes = console_routes(
        store, tenant=config.tenant, token=config.console_token,
        ttyd_base=config.ttyd_base or None, hub=hub,
        issues=issue_source, default_repo=config.default_repo,
    )
    routes.append(Route("/webhook", webhook, methods=["POST"]))
    return Starlette(routes=routes)
