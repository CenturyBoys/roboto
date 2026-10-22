"""Console web (D25) via httpx.ASGITransport — auth, isolamento por empresa, views e ações."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from roboto.app.session_hub import SessionHub
from roboto.orchestrator.model import Engine, Error, GithubEvent, InteractionKind, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok, Result
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


async def test_costs_by_execution_aggregation() -> None:
    store = InMemoryStore()
    for rid, tin in ((1, 100), (1, 50), (2, 10)):
        await store.record_llm_call(
            tenant="acme", run_id=rid, provider="openrouter", model="m", tier="t",
            tokens_in=tin, tokens_out=0, cost_usd=tin / 1000, now=_T0,
        )
    async with _client(store) as c:
        data = (await c.get("/costs", headers=_AUTH)).json()
        by = {e["run_id"]: e for e in data["by_execution"]}
        assert by[1]["tokens"] == 150 and by[2]["tokens"] == 10  # soma por execução


async def test_execution_detail_includes_cost() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    await store.record_llm_call(
        tenant="acme", run_id=run_id, provider="o", model="m", tier="t",
        tokens_in=300, tokens_out=200, cost_usd=0.5, now=_T0,
    )
    async with _client(store) as c:
        detail = (await c.get(f"/executions/{run_id}", headers=_AUTH)).json()
        assert detail["cost"] == {"tokens": 500, "cost_usd": 0.5}


async def test_pr_diff_endpoint() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    async with _client(store) as c:
        assert (await c.get(f"/executions/{run_id}/diff")).status_code == 401  # sem token
        empty = (await c.get(f"/executions/{run_id}/diff", headers=_AUTH)).json()
        assert empty["number"] is None and empty["diff"] == ""  # sem PR ainda
    await store.set_execution_pr(run_id, 42, "https://gh/x/pull/42", "diff --git\n+ok", _T0)
    async with _client(store) as c:
        d = (await c.get(f"/executions/{run_id}/diff", headers=_AUTH)).json()
        assert d["number"] == 42 and "+ok" in d["diff"]


class _FakeIssues:
    def __init__(self, items: list[tuple[int, str]]) -> None:
        self._items = items

    async def list_open_issues(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str]], Error]:
        return Ok(self._items)


async def test_issues_endpoint_lists_open() -> None:
    store = InMemoryStore()
    src = _FakeIssues([(180, "rate limit distribuído"), (112, "targeting por parceiro")])
    app = build_console(store, tenant="acme", token=_TOKEN, issues=src, default_repo="acme/app")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://console"
    ) as c:
        assert (await c.get("/issues")).status_code == 401  # exige token
        data = (await c.get("/issues", headers=_AUTH)).json()
        assert data["repo"] == "acme/app"
        assert [i["number"] for i in data["issues"]] == [180, 112]
        assert data["issues"][0]["title"] == "rate limit distribuído"


async def test_issues_endpoint_unconfigured() -> None:
    store = InMemoryStore()
    async with _client(store) as c:  # sem issue source nem repo
        data = (await c.get("/issues", headers=_AUTH)).json()
        assert data["issues"] == [] and "note" in data


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


async def test_answer_interaction_from_console() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    it = await store.create_interaction("acme", run_id, InteractionKind.QUESTION, "qual?", [], _T0)
    path = f"/interactions/{it.id}/answer"
    async with _client(store) as c:
        assert (await c.post(path, json={"answer": "x"})).status_code == 401  # sem token
        assert (await c.post(path, headers=_AUTH, json={"answer": " "})).status_code == 400  # vazio
        ausente = await c.post("/interactions/9999/answer", headers=_AUTH, json={"answer": "x"})
        assert ausente.status_code == 404
        ok = await c.post(path, headers=_AUTH, json={"answer": "Redis"})
        assert ok.status_code == 200
        assert ok.json() == {"id": it.id, "accepted": True, "status": "answered"}
        segunda = (await c.post(path, headers=_AUTH, json={"answer": "DB"})).json()
        assert segunda["accepted"] is False  # 1ª resposta válida vence (§6)
    answered = await store.get_interaction(it.id)
    assert answered is not None and answered.answer == "Redis"


def _client_hub(store: InMemoryStore, hub: SessionHub) -> httpx.AsyncClient:
    app = build_console(store, tenant="acme", token=_TOKEN, hub=hub)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://console")


async def test_steer_requires_live_session() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    hub = SessionHub()
    async with _client_hub(store, hub) as c:
        semvivo = await c.post(f"/executions/{run_id}/message", headers=_AUTH, json={"text": "oi"})
        assert semvivo.status_code == 409  # sessão não está viva
        live = hub.open(run_id)
        ok = await c.post(f"/executions/{run_id}/message", headers=_AUTH, json={"text": "muda X"})
        assert ok.status_code == 200
        assert await live.next_input() == "muda X"


async def test_interrupt_live_session() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    hub = SessionHub()
    live = hub.open(run_id)
    async with _client_hub(store, hub) as c:
        r = await c.post(f"/executions/{run_id}/interrupt", headers=_AUTH)
        assert r.status_code == 200
    assert live.interrupt_requested is True


async def test_answer_resolves_tool_approval() -> None:
    store = InMemoryStore()
    run_id = await _seed(store)
    it = await store.create_interaction(
        "acme", run_id, InteractionKind.APPROVAL, "Aprovar Bash?", ["aprovar", "negar"], _T0
    )
    hub = SessionHub()
    live = hub.open(run_id)
    fut = live.request_approval(it.id)
    async with _client_hub(store, hub) as c:
        r = await c.post(f"/interactions/{it.id}/answer", headers=_AUTH, json={"answer": "aprovar"})
        assert r.status_code == 200
    assert fut.done() and fut.result() is True  # can_use_tool acordado com allow


async def test_answer_interaction_tenant_isolation() -> None:
    store = InMemoryStore()
    other_run = await _seed(store, tenant="other", key="k2")
    it = await store.create_interaction("other", other_run, InteractionKind.QUESTION, "q", [], _T0)
    async with _client(store) as c:  # console é do tenant acme
        resp = await c.post(f"/interactions/{it.id}/answer", headers=_AUTH, json={"answer": "x"})
        assert resp.status_code == 404


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
