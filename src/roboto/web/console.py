"""Console web operacional (D25) — mesma store do Telegram (sem estado próprio).

Rotas de leitura + ações autorizadas sobre as execuções. Auth por **bearer token** e **isolamento
por empresa** (tenant do processo, D17): um run de outra empresa responde 404. `console_routes`
devolve a lista de rotas para compor com o webhook no mesmo app ASGI (ver `web/app.py`).
O terminal tmux (ttyd/Wetty) é infra à parte; aqui só devolvemos a URL configurada.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from roboto.orchestrator.model import Interaction, LlmCall, Run, RunState, Session, SessionEvent
from roboto.orchestrator.store import Store
from roboto.web.viewer import VIEWER_HTML

# SPA buildado pelo front (web/ui → vite build). Se presente, o console serve o app React; senão,
# cai no viewer legado embutido (dev/teste sem Node não quebram). Ver research/O §7.
_STATIC_DIR = Path(__file__).parent / "static"
_SPA_INDEX = _STATIC_DIR / "index.html"
_SPA_ASSETS = _STATIC_DIR / "assets"

# favicon: raio ⚡ (amarelo Potter) em quadrado escuro arredondado
_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<rect width='32' height='32' rx='7' fill='#0f1115'/>"
    "<path d='M19 3 L8 18 h6 l-3 11 L24 13 h-7 z' fill='#ffd21e'/></svg>"
)

# PWA (Fatia 1, trilha O): manifest + service worker tornam o console instalável na máquina e
# acessível por VPN como app. O ícone reusa o favicon SVG (purpose any+maskable).
_MANIFEST_JSON = (
    '{"name":"Potter · console","short_name":"Potter",'
    '"description":"Cockpit do fleet roboto","start_url":"/","scope":"/",'
    '"display":"standalone","background_color":"#0f1115","theme_color":"#0f1115",'
    '"icons":[{"src":"/favicon.svg","sizes":"any","type":"image/svg+xml","purpose":"any"},'
    '{"src":"/favicon.svg","sizes":"any","type":"image/svg+xml","purpose":"maskable"}]}'
)

# O service worker cacheia SÓ o shell (navegação) p/ abrir offline; dados/API vão SEMPRE à rede —
# carregam o bearer e nunca podem ser cacheados. Ter um handler de fetch é o que torna instalável.
_SERVICE_WORKER_JS = """\
const SHELL='potter-shell-v1';
self.addEventListener('install',e=>{e.waitUntil(caches.open(SHELL).then(c=>c.add('/')));
 self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(
 ks.filter(k=>k!==SHELL).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{ if(e.request.mode==='navigate'){
 e.respondWith(fetch(e.request).catch(()=>caches.match('/'))); } });
"""


def _run_dict(run: Run) -> dict[str, object]:
    return {
        "id": run.id,
        "tenant": run.tenant,
        "repo": run.repo,
        "issue_id": run.issue_id,
        "agent": run.agent,
        "state": str(run.state),
        "attempt": run.attempt,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _session_dict(session: Session) -> dict[str, object]:
    return {
        "id": session.id,
        "engine": str(session.engine),
        "native_session_id": session.native_session_id,
        "state": session.state,
    }


def _interaction_dict(it: Interaction) -> dict[str, object]:
    return {
        "id": it.id,
        "execution_id": it.execution_id,
        "kind": str(it.kind),
        "prompt": it.prompt,
        "options": it.options,
        "status": str(it.status),
        "answer": it.answer,
        "answered_by": it.answered_by,
    }


def _event_dict(e: SessionEvent) -> dict[str, object]:
    return {"id": e.id, "kind": e.kind, "text": e.text, "tool": e.tool, "at": e.at.isoformat()}


def _llm_dict(c: LlmCall) -> dict[str, object]:
    return {
        "run_id": c.run_id,
        "model": c.model,
        "tier": c.tier,
        "tokens_in": c.tokens_in,
        "tokens_out": c.tokens_out,
        "cost_usd": round(c.cost_usd, 6),
        "at": c.at.isoformat(),
    }


async def _viewer(request: Request) -> HTMLResponse:
    # SPA buildado se existir; senão, viewer legado. Dados sempre exigem o bearer (via JS).
    if _SPA_INDEX.is_file():
        return HTMLResponse(_SPA_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(VIEWER_HTML)


async def _favicon(request: Request) -> Response:
    return Response(_FAVICON_SVG, media_type="image/svg+xml")


async def _manifest(request: Request) -> Response:  # PWA (público; não expõe dado)
    return Response(_MANIFEST_JSON, media_type="application/manifest+json")


async def _service_worker(request: Request) -> Response:  # PWA (público)
    return Response(_SERVICE_WORKER_JS, media_type="text/javascript")


def shell_routes() -> list[BaseRoute]:
    """Rotas públicas do app-shell (SPA + PWA), compartilhadas pelo console e pelo setup."""
    routes: list[BaseRoute] = [
        Route("/", _viewer),
        Route("/favicon.svg", _favicon),
        Route("/favicon.ico", _favicon),
        Route("/manifest.webmanifest", _manifest),
        Route("/sw.js", _service_worker),
    ]
    if _SPA_ASSETS.is_dir():  # assets hasheados do vite (só montados quando há build)
        routes.append(Mount("/assets", app=StaticFiles(directory=str(_SPA_ASSETS))))
    return routes


def console_routes(
    store: Store, *, tenant: str, token: str, ttyd_base: str | None = None
) -> list[BaseRoute]:
    def _unauthorized(request: Request) -> bool:
        return not token or request.headers.get("authorization") != f"Bearer {token}"

    async def _owned_run(request: Request) -> Run | None:
        run = await store.get_run(int(request.path_params["run_id"]))
        return run if run is not None and run.tenant == tenant else None  # isolamento (D17)

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "mode": "running"})  # front distingue de "setup"

    async def costs(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        calls = await store.llm_calls(tenant, 100)
        tokens = sum(c.tokens_in + c.tokens_out for c in calls)
        cost = sum(c.cost_usd for c in calls)
        return JSONResponse(
            {"calls": [_llm_dict(c) for c in calls], "totals": {"tokens": tokens, "cost_usd": cost}}
        )

    async def list_executions(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        runs = await store.list_runs(tenant, 100)
        return JSONResponse({"executions": [_run_dict(r) for r in runs]})

    async def execution_detail(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        sessions = await store.sessions_for_execution(run.id)
        interactions = await store.interactions_for_execution(run.id)
        return JSONResponse(
            {
                "execution": _run_dict(run),
                "sessions": [_session_dict(s) for s in sessions],
                "interactions": [_interaction_dict(i) for i in interactions],
            }
        )

    async def pending_interactions(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        items = await store.pending_interactions(tenant, 100)
        return JSONResponse({"interactions": [_interaction_dict(i) for i in items]})

    async def answer_interaction(request: Request) -> JSONResponse:
        # Responder HITL pelo cockpit (Fatia 3) — mesmo answer_interaction do Telegram (1ª vence).
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        iid = int(request.path_params["interaction_id"])
        it = await store.get_interaction(iid)
        if it is None or it.tenant != tenant:  # isolamento por empresa (D17)
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        answer = str(body.get("answer", "")).strip() if isinstance(body, dict) else ""
        if not answer:
            return JSONResponse({"error": "answer vazio"}, status_code=400)
        accepted = await store.answer_interaction(iid, answer, "console", datetime.now(UTC))
        return JSONResponse(
            {"id": iid, "accepted": accepted, "status": "answered" if accepted else str(it.status)}
        )

    async def cancel(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        await store.set_state(run.id, RunState.FAILED, datetime.now(UTC))
        return JSONResponse({"id": run.id, "state": str(RunState.FAILED)})

    async def retry(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        await store.set_state(run.id, RunState.QUEUED, datetime.now(UTC), attempt=run.attempt + 1)
        return JSONResponse({"id": run.id, "state": str(RunState.QUEUED)})

    async def terminal(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        url = ttyd_base.rstrip("/") if ttyd_base else None
        return JSONResponse(
            {"terminal_url": url, "note": "terminal do container (ttyd+tmux); isolado por empresa"}
        )

    async def events_stream(request: Request) -> Response:
        # Feed ao vivo (SSE, Fatia 2): backlog + novos eventos do motor. Bearer + isolamento (D17).
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        run_id = run.id

        async def gen() -> AsyncIterator[bytes]:
            cursor = 0
            while not await request.is_disconnected():
                for e in await store.session_events(run_id, cursor, 200):
                    cursor = e.id
                    yield f"data: {json.dumps(_event_dict(e))}\n\n".encode()
                yield b": ping\n\n"  # heartbeat: mantem a conexao viva entre polls
                await asyncio.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return [
        *shell_routes(),
        Route("/healthz", healthz),
        Route("/executions", list_executions),
        Route("/executions/{run_id:int}", execution_detail),
        Route("/executions/{run_id:int}/cancel", cancel, methods=["POST"]),
        Route("/executions/{run_id:int}/retry", retry, methods=["POST"]),
        Route("/executions/{run_id:int}/terminal", terminal),
        Route("/executions/{run_id:int}/events", events_stream),
        Route("/interactions", pending_interactions),
        Route("/interactions/{interaction_id:int}/answer", answer_interaction, methods=["POST"]),
        Route("/costs", costs),
    ]


def build_console(
    store: Store, *, tenant: str, token: str, ttyd_base: str | None = None
) -> Starlette:
    return Starlette(routes=console_routes(store, tenant=tenant, token=token, ttyd_base=ttyd_base))
