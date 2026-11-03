"""Rascunho durável do breakdown (#203, inc. 5): store round-trip + endpoints GET/PUT/DELETE."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from roboto.github.app import IssueRef
from roboto.orchestrator.model import Error
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok, Result
from roboto.web.console import build_console

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = "console-secret"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


async def test_store_draft_roundtrip() -> None:
    store = InMemoryStore()
    assert await store.get_breakdown_draft("acme", "acme/app", "66") is None
    await store.set_breakdown_draft("acme", "acme/app", "66", '[{"title":"x"}]', _T0)
    assert await store.get_breakdown_draft("acme", "acme/app", "66") == '[{"title":"x"}]'
    # isolado por (tenant, repo, issue)
    assert await store.get_breakdown_draft("other", "acme/app", "66") is None
    await store.delete_breakdown_draft("acme", "acme/app", "66")
    assert await store.get_breakdown_draft("acme", "acme/app", "66") is None


class _Issues:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self._next = 300

    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]:
        n = self._next
        self._next += 1
        self.created.append((title, body))
        return Ok(IssueRef(repo=repo, number=n, url=f"https://x/{n}"))

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]:
        return Ok(None)


def _console(store: InMemoryStore, **kw: object) -> httpx.AsyncClient:
    app = build_console(store, tenant="acme", token=_TOKEN, **kw)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://console")


async def test_draft_endpoints_persist_across_requests() -> None:
    store = InMemoryStore()
    async with _console(store, default_repo="acme/app") as c:
        # vazio no começo
        assert (await c.get("/issues/66/breakdown/draft", headers=_AUTH)).json()["items"] is None
        # salva (PUT)
        items = [{"title": "ADR", "points": ["x"], "depends_on_prev": False}]
        r = await c.put("/issues/66/breakdown/draft", headers=_AUTH, json={"items": items})
        assert r.status_code == 200
        # recupera (GET) — simula F5 / outro dispositivo (mesmo store/backend)
        got = (await c.get("/issues/66/breakdown/draft", headers=_AUTH)).json()
        assert got["items"] == items
        # descarta (DELETE)
        await c.delete("/issues/66/breakdown/draft", headers=_AUTH)
        assert (await c.get("/issues/66/breakdown/draft", headers=_AUTH)).json()["items"] is None


async def test_draft_requires_auth() -> None:
    store = InMemoryStore()
    async with _console(store, default_repo="acme/app") as c:
        assert (await c.get("/issues/66/breakdown/draft")).status_code == 401
        assert (await c.put("/issues/66/breakdown/draft", json={"items": []})).status_code == 401


async def test_apply_clears_draft() -> None:
    store = InMemoryStore()
    await store.set_breakdown_draft("acme", "acme/app", "66", '[{"title":"ADR"}]', _T0)
    async with _console(store, issues=_Issues(), default_repo="acme/app") as c:
        payload = {"items": [{"title": "ADR", "points": [], "depends_on_prev": False}]}
        r = await c.post("/issues/66/breakdown/apply", headers=_AUTH, json=payload)
        assert r.status_code == 200
    # materializou → rascunho apagado (não reabre uma proposta já criada)
    assert await store.get_breakdown_draft("acme", "acme/app", "66") is None
