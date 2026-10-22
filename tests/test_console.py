"""Console web (D25) via httpx.ASGITransport — auth, isolamento por empresa, views e ações."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from roboto.orchestrator.model import Engine, GithubEvent, InteractionKind, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.web.console import build_console

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = "console-secret"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


async def _seed(store: InMemoryStore, tenant: str = "acme", key: str = "k") -> int:
    event = GithubEvent(
        tenant=tenant, repo=f"{tenant}/app", issue_id="7", agent="impl", idempotency_key=key
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    return run.id


def _client(store: InMemoryStore) -> httpx.AsyncClient:
    app = build_console(store, tenant="acme", token=_TOKEN)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://console")


async def test_healthz_is_public() -> None:
    store = InMemoryStore()
    async with _client(store) as c:
        resp = await c.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "mode": "running"}  # front distingue de "setup"


async def test_viewer_is_served() -> None:
    store = InMemoryStore()
    async with _client(store) as c:
        resp = await c.get("/")
        assert resp.status_code == 200
        assert "Potter" in resp.text  # a página (dados exigem o token via JS)
        fav = await c.get("/favicon.svg")
        assert fav.status_code == 200
        assert fav.headers["content-type"].startswith("image/svg")
        assert "path" in fav.text  # o raio


async def test_pwa_manifest_and_service_worker_are_public() -> None:
    store = InMemoryStore()
    async with _client(store) as c:
        man = await c.get("/manifest.webmanifest")  # público: não exige token
        assert man.status_code == 200
        assert man.headers["content-type"].startswith("application/manifest+json")
        assert '"display":"standalone"' in man.text and "/favicon.svg" in man.text
        sw = await c.get("/sw.js")
        assert sw.status_code == 200
        assert "javascript" in sw.headers["content-type"]
        assert "addEventListener('fetch'" in sw.text  # handler = pré-requisito de instalável


async def test_served_page_references_pwa_manifest() -> None:
    # Vale para o SPA buildado OU o fallback legado: ambos referenciam o manifest e a marca.
    store = InMemoryStore()
    async with _client(store) as c:
        page = (await c.get("/")).text
        assert "Potter" in page and "manifest.webmanifest" in page


def test_legacy_viewer_has_pwa_and_cockpit_hooks() -> None:
    # Fallback embutido (sem build Node): segue PWA + terminal embutido + auto-refresh (Fatia 1).
    from roboto.web.viewer import VIEWER_HTML

    assert "register('/sw.js')" in VIEWER_HTML and "toggleAuto" in VIEWER_HTML
    assert "class=term" in VIEWER_HTML and 'rel="manifest"' in VIEWER_HTML


async def test_serves_legacy_viewer_when_spa_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Sem build do SPA (dev/checkout sem Node), o console cai no viewer legado embutido.
    import roboto.web.console as console_mod

    monkeypatch.setattr(console_mod, "_SPA_INDEX", Path("/nao/existe/index.html"))
    store = InMemoryStore()
    async with _client(store) as c:
        page = (await c.get("/")).text
        assert "toggleAuto" in page  # marca do viewer legado


async def test_costs_endpoint() -> None:
    store = InMemoryStore()
    await store.record_llm_call(
        tenant="acme", run_id=1, provider="openrouter", model="qwen/qwen3-coder",
        tier="frontier", tokens_in=1000, tokens_out=200, cost_usd=0.48, now=_T0,
    )
    async with _client(store) as c:
        assert (await c.get("/costs")).status_code == 401  # exige token
        data = (await c.get("/costs", headers=_AUTH)).json()
        assert data["totals"]["tokens"] == 1200
        assert len(data["calls"]) == 1


async def test_requires_auth() -> None:
    store = InMemoryStore()
    await _seed(store)
    async with _client(store) as c:
        assert (await c.get("/executions")).status_code == 401
        assert (await c.get("/executions", headers=_AUTH)).status_code == 200


async def test_list_and_detail() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    session = await store.create_session("acme", run_id, Engine.CLAUDE_CODE, _T0)
    await store.set_native_session(session.id, "nat-1", _T0)
    await store.create_interaction(
        "acme", run_id, InteractionKind.DECISION, "Redis ou DB?", ["Redis", "DB"], _T0
    )
    async with _client(store) as c:
        listing = (await c.get("/executions", headers=_AUTH)).json()
        assert [e["id"] for e in listing["executions"]] == [run_id]
        detail = (await c.get(f"/executions/{run_id}", headers=_AUTH)).json()
        assert detail["execution"]["repo"] == "acme/app"
        assert detail["sessions"][0]["native_session_id"] == "nat-1"
        assert detail["interactions"][0]["prompt"] == "Redis ou DB?"


async def test_tenant_isolation_returns_404() -> None:
    store = InMemoryStore()
    other = await _seed(store, tenant="other", key="k2")  # run de outra empresa
    async with _client(store) as c:  # console é do tenant "acme"
        assert (await c.get(f"/executions/{other}", headers=_AUTH)).status_code == 404
        assert (await c.post(f"/executions/{other}/cancel", headers=_AUTH)).status_code == 404


async def test_cancel_and_retry_change_state() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    async with _client(store) as c:
        cancelled = await c.post(f"/executions/{run_id}/cancel", headers=_AUTH)
        assert cancelled.json()["state"] == str(RunState.FAILED)
        assert store._runs[run_id].state is RunState.FAILED
        retried = await c.post(f"/executions/{run_id}/retry", headers=_AUTH)
        assert retried.json()["state"] == str(RunState.QUEUED)
        assert store._runs[run_id].state is RunState.QUEUED
        assert store._runs[run_id].attempt == 1


async def test_session_events_store_filters_by_after_id() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    e1 = await store.append_session_event("acme", run_id, "message", _T0, text="oi")
    await store.append_session_event("acme", run_id, "tool_call", _T0, tool="Bash")
    novos = await store.session_events(run_id, e1.id, 100)  # só o que veio depois do e1
    assert [e.kind for e in novos] == ["tool_call"]


async def test_events_endpoint_auth_and_isolation() -> None:
    # Auth/isolamento retornam ANTES de abrir o stream (seguro no ASGITransport). O streaming em si
    # (backlog + live) é validado via uvicorn real no E2E Docker — ASGITransport não encerra SSE.
    store = InMemoryStore()
    run_id = await _seed(store)
    other = await _seed(store, tenant="other", key="k2")
    async with _client(store) as c:
        assert (await c.get(f"/executions/{run_id}/events")).status_code == 401  # sem token
        assert (await c.get(f"/executions/{other}/events", headers=_AUTH)).status_code == 404


async def test_pending_interactions_and_terminal() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    await store.create_interaction(
        "acme", run_id, InteractionKind.QUESTION, "qual?", [], _T0
    )
    app = build_console(store, tenant="acme", token=_TOKEN, ttyd_base="https://term.acme/")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://console"
    ) as c:
        pend = (await c.get("/interactions", headers=_AUTH)).json()
        assert len(pend["interactions"]) == 1
        term = (await c.get(f"/executions/{run_id}/terminal", headers=_AUTH)).json()
        assert term["terminal_url"] == "https://term.acme"  # terminal compartilhado (tmux único)
