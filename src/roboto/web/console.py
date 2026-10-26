"""Console web operacional (D25) — mesma store do Telegram (sem estado próprio).

Rotas de leitura + ações autorizadas sobre as execuções. Auth por **bearer token** e **isolamento
por empresa** (tenant do processo, D17): um run de outra empresa responde 404. `console_routes`
devolve a lista de rotas para compor com o webhook no mesmo app ASGI (ver `web/app.py`).
O terminal tmux (ttyd/Wetty) é infra à parte; aqui só devolvemos a URL configurada.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from roboto.agents.refiner import IssueDraft, converse
from roboto.agents.review import check_issue_readiness
from roboto.app.loops import ISSUE_BODY_END, ISSUE_BODY_START
from roboto.app.session_hub import SessionHub
from roboto.app.tmux_copilot import session_name
from roboto.llm.port import ModelGateway
from roboto.orchestrator.model import (
    Error,
    GithubEvent,
    Interaction,
    InteractionKind,
    LlmCall,
    Run,
    RunState,
    Session,
    SessionEvent,
)
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result
from roboto.web.viewer import VIEWER_HTML


def _extract_proposal(msgs: list[str]) -> str:
    """Corpo LIMPO da issue a partir das mensagens do motor (pré-preenche o "📝 Aplicar na issue").

    1) Preferência: o trecho ENTRE os marcadores `===ISSUE-INICIO===`/`===ISSUE-FIM===` da última
       mensagem que os tiver — é o corpo sem preâmbulo ("vou propor…") nem comentário. Ancora no
       MIOLO (`ISSUE-INICIO`/`ISSUE-FIM`) porque o modelo às vezes quebra os `===` numa linha à
       parte (markdown trata `===` como régua); a decoração `===` das bordas é removida.
    2) Fallback (runs antigos / refino via chat, sem marcadores): a última mensagem que PARECE uma
       issue refinada (seções/critérios); senão a mais longa. Evita pegar conversa curta ou erro.
    """
    start = ISSUE_BODY_START.strip("=")  # "ISSUE-INICIO" — miolo estável, imune à quebra dos `===`
    end = ISSUE_BODY_END.strip("=")
    for text in reversed(msgs):
        if start in text:
            inner = text.split(start, 1)[1].split(end, 1)[0]
            cleaned = inner.strip().strip("=").strip()
            if cleaned:
                return cleaned
    # descarta mensagens de ERRO (ex.: "selected model ... may not exist"): um refino que falhou não
    # pode virar "proposta" no textarea do aplicar — melhor devolver vazio do que o texto do erro.
    usable = [m for m in msgs if not _looks_like_error(m)]
    markers = ("Critérios de aceite", "## Contexto", "Definition of Done", "Escopo", "DoD")
    looks_like = [m for m in usable if any(k in m for k in markers)]
    return looks_like[-1] if looks_like else (max(usable, key=len) if usable else "")


def _looks_like_error(text: str) -> bool:
    low = text.lower()
    return any(
        s in low
        for s in (
            "may not exist or you may not have access",
            "selected model",
            "api error",
            "error from provider",
        )
    )


class IssueSource(Protocol):
    """O que o console usa do GitHub: issues abertas (com labels) e o corpo de uma issue."""

    async def list_open_issues_rich(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str, list[str]]], Error]: ...

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]: ...

    async def update_issue(
        self, repo: str, number: int, *, title: str, body: str
    ) -> Result[None, Error]: ...

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]: ...

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


_APPROVE_WORDS = {"aprovar", "approve", "allow", "sim", "yes", "ok"}


def console_routes(
    store: Store,
    *,
    tenant: str,
    token: str,
    ttyd_base: str | None = None,
    hub: SessionHub | None = None,
    issues: IssueSource | None = None,
    default_repo: str = "",
    gateway: ModelGateway | None = None,
    start_session: Callable[[Run, str], Awaitable[bool]] | None = None,
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
        agg: dict[int, list[float]] = {}  # run_id -> [tokens, cost] (Fatia 4: custo por execução)
        for c in calls:
            if c.run_id is None:
                continue
            acc = agg.setdefault(c.run_id, [0.0, 0.0])
            acc[0] += c.tokens_in + c.tokens_out
            acc[1] += c.cost_usd
        by_execution = [
            {"run_id": rid, "tokens": int(t[0]), "cost_usd": round(t[1], 6)}
            for rid, t in sorted(agg.items(), reverse=True)
        ]
        return JSONResponse(
            {
                "calls": [_llm_dict(c) for c in calls],
                "totals": {"tokens": tokens, "cost_usd": cost},
                "by_execution": by_execution,
            }
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
        tokens, cost = await store.cost_for_execution(run.id)  # custo da execução (Fatia 4)
        live = hub is not None and hub.get(run.id) is not None  # co-piloto só em sessão interativa
        return JSONResponse(
            {
                "execution": _run_dict(run),
                "sessions": [_session_dict(s) for s in sessions],
                "interactions": [_interaction_dict(i) for i in interactions],
                "cost": {"tokens": tokens, "cost_usd": round(cost, 6)},
                "live": live,
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
        # Co-piloto (Fatia 5): se for aprovação de ferramenta, acorda o can_use_tool que espera.
        if accepted and hub is not None and it.kind is InteractionKind.APPROVAL:
            live = hub.get(it.execution_id)
            if live is not None:
                live.resolve_approval(iid, answer.strip().lower() in _APPROVE_WORDS)
        return JSONResponse(
            {"id": iid, "accepted": accepted, "status": "answered" if accepted else str(it.status)}
        )

    async def steer_message(request: Request) -> JSONResponse:
        # Co-piloto (Fatia 5): manda uma mensagem p/ a sessão VIVA do motor (steer a qualquer hora).
        # Se ainda NÃO há sessão viva, abre uma sob demanda (liga o driver interativo) usando esta
        # mensagem como prompt inicial — é o que faz "conversar com a sessão viva" funcionar.
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await request.json()
        text = str(body.get("text", "")).strip() if isinstance(body, dict) else ""
        if not text:
            return JSONResponse({"error": "text vazio"}, status_code=400)
        # registra a mensagem do humano no thread (kind "user") — o chat mostra os dois lados
        await store.append_session_event(run.tenant, run.id, "user", datetime.now(UTC), text=text)
        live = hub.get(run.id) if hub is not None else None
        if live is not None:  # sessão já viva: enfileira o steer p/ o próximo turno
            await live.steer(text)
            return JSONResponse({"ok": True, "live": True})
        if start_session is None:  # driver interativo não disponível (ex.: motor stub)
            return JSONResponse({"error": "sessão não está viva"}, status_code=409)
        started = await start_session(run, text)
        if not started:  # ocupado pelo ciclo automático — não abrir 2 motores no mesmo workdir
            return JSONResponse(
                {
                    "error": "run ocupado pelo ciclo automático; "
                    "aguarde ou cancele p/ abrir a sessão viva"
                },
                status_code=409,
            )
        return JSONResponse({"ok": True, "live": True, "started": True}, status_code=202)

    async def interrupt_session(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        live = hub.get(run.id) if hub is not None else None
        if live is None:
            return JSONResponse({"error": "sessão não está viva"}, status_code=409)
        live.request_interrupt()
        return JSONResponse({"ok": True})

    async def end_session(request: Request) -> JSONResponse:
        # Encerrar a sessão viva (co-piloto): acaba a conversa; o driver sai do laço e fecha.
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        live = hub.get(run.id) if hub is not None else None
        if live is None:
            return JSONResponse({"error": "sessão não está viva"}, status_code=409)
        live.request_end()
        return JSONResponse({"ok": True})

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
        # anexa NA tmux por-run (ttyd -a url-arg): você vê/opera a sessão REAL do motor. Se a sessão
        # não existir (modo sdk / sem chat aberto), o wrapper do ttyd cai no terminal padrão.
        url = f"{ttyd_base.rstrip('/')}/?arg={session_name(run.id)}" if ttyd_base else None
        return JSONResponse(
            {"terminal_url": url, "note": "terminal da sessão viva (tmux por-run); anexa no motor"}
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

    async def pr_diff(request: Request) -> JSONResponse:
        # Diff do PR da execução (Fatia 4) — cacheado no banco pelo ciclo de review; a UI só lê.
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        pr = await store.get_execution_pr(run.id)
        if pr is None:
            return JSONResponse({"number": None, "url": None, "diff": ""})
        return JSONResponse({"number": pr.number, "url": pr.url, "diff": pr.diff})

    async def list_issues(request: Request) -> JSONResponse:
        # Issues abertas do repo — entry point do refino no cockpit (Fatia 6).
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        repo = request.query_params.get("repo") or default_repo
        if issues is None or not repo:
            return JSONResponse({"repo": repo, "issues": [], "note": "GitHub não configurado"})
        result = await issues.list_open_issues_rich(repo, limit=50)
        if isinstance(result, Err):
            return JSONResponse({"repo": repo, "issues": [], "error": result.error.message})
        return JSONResponse(
            {
                "repo": repo,
                "issues": [
                    {"number": n, "title": t, "labels": lbls} for n, t, lbls in result.value
                ],
            }
        )

    async def issue_detail(request: Request) -> JSONResponse:
        # Corpo da issue + check de DoR (determinístico, sem LLM) — base do refino (Fatia 6).
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        repo = request.query_params.get("repo") or default_repo
        number = int(request.path_params["number"])
        if issues is None or not repo:
            return JSONResponse({"error": "GitHub não configurado"}, status_code=409)
        got = await issues.get_issue(repo, number)
        if isinstance(got, Err):
            return JSONResponse({"error": got.error.message}, status_code=502)
        title, body = got.value
        v = check_issue_readiness(IssueDraft(title=title, body=body))
        return JSONResponse(
            {
                "number": number,
                "title": title,
                "body": body,
                "dor": {"ready": v.ready, "missing": v.missing},
            }
        )

    async def issue_refine(request: Request) -> JSONResponse:
        # Conversa de refino (refiner/OpenRouter): transcript -> pergunta OU rascunho (Fatia 6).
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if gateway is None:
            return JSONResponse({"error": "modelo não configurado"}, status_code=409)
        payload = await request.json()
        raw = payload.get("transcript", []) if isinstance(payload, dict) else []
        transcript = [
            (str(t[0]), str(t[1])) for t in raw if isinstance(t, list) and len(t) == 2
        ]
        step = await converse(transcript, gateway)
        if isinstance(step, Err):
            return JSONResponse({"error": step.error.message}, status_code=502)
        s = step.value
        if s.draft is not None:
            v = check_issue_readiness(s.draft)
            return JSONResponse(
                {
                    "question": None,
                    "draft": {"title": s.draft.title, "body": s.draft.body},
                    "dor": {"ready": v.ready, "missing": v.missing},
                }
            )
        return JSONResponse({"question": s.question, "draft": None})

    async def refine_with_engine(request: Request) -> JSONResponse:
        # Refino engine-scoped (Fatia 6/C): enfileira run que o motor pega p/ ler o repo e propor.
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        repo = request.query_params.get("repo") or default_repo
        number = int(request.path_params["number"])
        if not repo:
            return JSONResponse({"error": "repo não configurado"}, status_code=409)
        when = datetime.now(UTC)
        ev = GithubEvent(
            tenant=tenant,
            repo=repo,
            issue_id=str(number),
            agent="refine",
            idempotency_key=f"refine:{repo}:{number}:{when.isoformat()}",
        )
        run, _ = await store.insert_run_if_absent(ev, when)
        return JSONResponse({"run_id": run.id})

    async def implement_with_engine(request: Request) -> JSONResponse:
        # Executar a issue PELO cockpit: enfileira um run `agent='impl'` que o `process_pr_run_tick`
        # pega p/ codar e abrir PR. Local, a label `roboto` NÃO dispara (é webhook, precisa URL
        # pública); aqui o gatilho é este botão. Gate de DoR (issue-first): só coda issue PRONTA.
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        repo = request.query_params.get("repo") or default_repo
        number = int(request.path_params["number"])
        if not repo:
            return JSONResponse({"error": "repo não configurado"}, status_code=409)
        if issues is None:
            return JSONResponse({"error": "GitHub não configurado"}, status_code=409)
        got = await issues.get_issue(repo, number)
        if isinstance(got, Err):
            return JSONResponse({"error": got.error.message}, status_code=502)
        title, body = got.value
        verdict = check_issue_readiness(IssueDraft(title=title, body=body))
        if not verdict.ready:
            return JSONResponse(
                {"error": "issue não está pronta (DoR)", "missing": verdict.missing},
                status_code=409,
            )
        # guard: recusa se já há impl ATIVO pra esta issue (evita duplo-clique / dois runs).
        # "Ativo" = ainda não terminou (queued/running/verifying).
        active_states = {RunState.QUEUED, RunState.RUNNING, RunState.VERIFYING}
        for r in await store.list_runs(tenant, 100):
            if (
                r.agent == "impl"
                and r.repo == repo
                and r.issue_id == str(number)
                and r.state in active_states
            ):
                return JSONResponse(
                    {"error": "já existe implementação ativa para esta issue", "run_id": r.id},
                    status_code=409,
                )
        when = datetime.now(UTC)
        ev = GithubEvent(
            tenant=tenant,
            repo=repo,
            issue_id=str(number),
            agent="impl",
            idempotency_key=f"impl:{repo}:{number}:{when.isoformat()}",
        )
        run, _ = await store.insert_run_if_absent(ev, when)
        return JSONResponse({"run_id": run.id})

    async def proposal(request: Request) -> JSONResponse:
        # Último texto do motor nesta execução = o rascunho proposto (pré-preenche o "aplicar").
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        events = await store.session_events(run.id, 0, 500)
        msgs = [e.text for e in events if e.kind == "message" and e.text.strip()]
        body = _extract_proposal(msgs)
        return JSONResponse({"body": body, "issue_id": run.issue_id})

    async def apply_proposal(request: Request) -> JSONResponse:
        # Aplica o corpo (editado pelo humano) na issue do GitHub + comentário de trilha (D30).
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        run = await _owned_run(request)
        if run is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if issues is None or not run.issue_id.isdigit():
            return JSONResponse({"error": "GitHub não configurado"}, status_code=409)
        payload = await request.json()
        body = str(payload.get("body", "")).strip() if isinstance(payload, dict) else ""
        if not body:
            return JSONResponse({"error": "body vazio"}, status_code=400)
        number = int(run.issue_id)
        got = await issues.get_issue(run.repo, number)
        title = got.value[0] if isinstance(got, Ok) else f"#{number}"
        res = await issues.update_issue(run.repo, number, title=title, body=body)
        if isinstance(res, Err):
            return JSONResponse({"error": res.error.message}, status_code=502)
        await issues.comment_pr(run.repo, number, "📝 Issue refinada pelo fleet (via cockpit).")
        return JSONResponse({"ok": True, "number": number})

    return [
        *shell_routes(),
        Route("/healthz", healthz),
        Route("/executions", list_executions),
        Route("/executions/{run_id:int}", execution_detail),
        Route("/executions/{run_id:int}/cancel", cancel, methods=["POST"]),
        Route("/executions/{run_id:int}/retry", retry, methods=["POST"]),
        Route("/executions/{run_id:int}/terminal", terminal),
        Route("/executions/{run_id:int}/events", events_stream),
        Route("/executions/{run_id:int}/diff", pr_diff),
        Route("/executions/{run_id:int}/message", steer_message, methods=["POST"]),
        Route("/executions/{run_id:int}/interrupt", interrupt_session, methods=["POST"]),
        Route("/executions/{run_id:int}/end", end_session, methods=["POST"]),
        Route("/issues", list_issues),
        Route("/issues/{number:int}", issue_detail),
        Route("/issues/{number:int}/refine", issue_refine, methods=["POST"]),
        Route("/issues/{number:int}/refine-engine", refine_with_engine, methods=["POST"]),
        Route("/issues/{number:int}/implement", implement_with_engine, methods=["POST"]),
        Route("/executions/{run_id:int}/proposal", proposal),
        Route("/executions/{run_id:int}/apply", apply_proposal, methods=["POST"]),
        Route("/interactions", pending_interactions),
        Route("/interactions/{interaction_id:int}/answer", answer_interaction, methods=["POST"]),
        Route("/costs", costs),
    ]


def build_console(
    store: Store,
    *,
    tenant: str,
    token: str,
    ttyd_base: str | None = None,
    hub: SessionHub | None = None,
    issues: IssueSource | None = None,
    default_repo: str = "",
    gateway: ModelGateway | None = None,
    start_session: Callable[[Run, str], Awaitable[bool]] | None = None,
) -> Starlette:
    return Starlette(
        routes=console_routes(
            store, tenant=tenant, token=token, ttyd_base=ttyd_base, hub=hub,
            issues=issues, default_repo=default_repo, gateway=gateway,
            start_session=start_session,
        )
    )
