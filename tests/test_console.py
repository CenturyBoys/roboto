"""Console web (D25) via httpx.ASGITransport — auth, isolamento por empresa, views e ações."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

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
        assert resp.json() == {"ok": True}


async def test_viewer_is_served() -> None:
    store = InMemoryStore()
    async with _client(store) as c:
        resp = await c.get("/")
        assert resp.status_code == 200
        assert "Potter" in resp.text  # a página (dados exigem o token via JS)


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
