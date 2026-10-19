"""Console web operacional (D25) — mesma store do Telegram (sem estado próprio).

Rotas de leitura + ações autorizadas sobre as execuções. Auth por **bearer token** e **isolamento
por empresa** (tenant do processo, D17): um run de outra empresa responde 404. `console_routes`
devolve a lista de rotas para compor com o webhook no mesmo app ASGI (ver `web/app.py`).
O terminal tmux (ttyd/Wetty) é infra à parte; aqui só devolvemos a URL configurada.
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from roboto.orchestrator.model import Interaction, Run, RunState, Session
from roboto.orchestrator.store import Store


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
        "kind": str(it.kind),
        "prompt": it.prompt,
        "options": it.options,
        "status": str(it.status),
        "answer": it.answer,
        "answered_by": it.answered_by,
    }


def console_routes(
    store: Store, *, tenant: str, token: str, ttyd_base: str | None = None
) -> list[Route]:
    def _unauthorized(request: Request) -> bool:
        return not token or request.headers.get("authorization") != f"Bearer {token}"

    async def _owned_run(request: Request) -> Run | None:
        run = await store.get_run(int(request.path_params["run_id"]))
        return run if run is not None and run.tenant == tenant else None  # isolamento (D17)

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

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
        url = f"{ttyd_base.rstrip('/')}/{run.id}" if ttyd_base else None
        return JSONResponse(
            {"terminal_url": url, "note": "ttyd/Wetty por container; autenticado e isolado (D25)"}
        )

    return [
        Route("/healthz", healthz),
        Route("/executions", list_executions),
        Route("/executions/{run_id:int}", execution_detail),
        Route("/executions/{run_id:int}/cancel", cancel, methods=["POST"]),
        Route("/executions/{run_id:int}/retry", retry, methods=["POST"]),
        Route("/executions/{run_id:int}/terminal", terminal),
        Route("/interactions", pending_interactions),
    ]


def build_console(
    store: Store, *, tenant: str, token: str, ttyd_base: str | None = None
) -> Starlette:
    return Starlette(routes=console_routes(store, tenant=tenant, token=token, ttyd_base=ttyd_base))
