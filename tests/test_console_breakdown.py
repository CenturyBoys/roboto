"""Endpoints de breakdown de épico no cockpit (#203, inc. 4): propor (sem criar) + aplicar (OK)."""

from __future__ import annotations

import httpx

from roboto.github.app import IssueRef
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok, Result
from roboto.web.console import build_console

_TOKEN = "console-secret"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
# corpo com sinais de épico: palavra "épico" + ≥8 checkboxes = is_epic True
_EPIC_BODY = "Este épico cobre várias frentes.\n" + "\n".join(f"- [ ] item {i}" for i in range(9))


class _Issues:
    def __init__(self, body: str) -> None:
        self._body = body
        self.created: list[tuple[str, str]] = []
        self.comments: list[tuple[int, str]] = []
        self._next = 300

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        return Ok((f"issue #{number}", self._body))

    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]:
        n = self._next
        self._next += 1
        self.created.append((title, body))
        return Ok(IssueRef(repo=repo, number=n, url=f"https://x/{n}"))

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]:
        self.comments.append((number, body))
        return Ok(None)


class _Gw:
    def __init__(self, text: str) -> None:
        self._t = text

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        return Ok(Completion(text=self._t, model="fake"))


def _console(store: InMemoryStore, **kw: object) -> httpx.AsyncClient:
    app = build_console(store, tenant="acme", token=_TOKEN, **kw)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://console")


async def test_propose_returns_items_without_creating() -> None:
    store = InMemoryStore()
    issues = _Issues(_EPIC_BODY)
    reply = "ITEM: ADR\n- escrever\nITEM: logger\n- mascarar PII\n"
    async with _console(store, issues=issues, default_repo="acme/app", gateway=_Gw(reply)) as c:
        body = (
            await c.post("/issues/66/breakdown", headers=_AUTH, json={"transcript": []})
        ).json()
    assert body["question"] is None
    assert [i["title"] for i in body["items"]] == ["ADR", "logger"]
    assert body["items"][1]["depends_on_prev"] is True
    assert issues.created == []  # PROPOR não cria nada (OK humano vem no /apply)


async def test_propose_rejects_non_epic() -> None:
    store = InMemoryStore()
    issues = _Issues("uma coisa só, sem sinais de épico")
    async with _console(
        store, issues=issues, default_repo="acme/app", gateway=_Gw("ITEM: x\n- y")
    ) as c:
        r = await c.post("/issues/66/breakdown", headers=_AUTH, json={})
    assert r.status_code == 409


async def test_propose_returns_question() -> None:
    store = InMemoryStore()
    issues = _Issues(_EPIC_BODY)
    async with _console(
        store, issues=issues, default_repo="acme/app", gateway=_Gw("PERGUNTA: quantos apps?")
    ) as c:
        body = (await c.post("/issues/66/breakdown", headers=_AUTH, json={})).json()
    assert body["items"] is None and "quantos apps" in body["question"]


async def test_apply_creates_chained_subissues() -> None:
    store = InMemoryStore()
    issues = _Issues(_EPIC_BODY)
    payload = {
        "items": [
            {"title": "ADR", "points": ["escrever"], "depends_on_prev": False},
            {"title": "logger", "points": ["mascarar PII"], "depends_on_prev": True},
        ]
    }
    async with _console(store, issues=issues, default_repo="acme/app") as c:
        body = (
            await c.post("/issues/66/breakdown/apply", headers=_AUTH, json=payload)
        ).json()
    assert [x["number"] for x in body["created"]] == [300, 301]
    assert "Depende de #300" in issues.created[1][1]  # 2ª encadeia na 1ª
    assert "épico #66" in issues.created[0][1]  # referencia o épico
    assert issues.comments and issues.comments[0][0] == 66  # índice comentado no épico


async def test_apply_requires_items() -> None:
    store = InMemoryStore()
    issues = _Issues(_EPIC_BODY)
    async with _console(store, issues=issues, default_repo="acme/app") as c:
        r = await c.post("/issues/66/breakdown/apply", headers=_AUTH, json={"items": []})
    assert r.status_code == 400


async def test_breakdown_requires_auth() -> None:
    store = InMemoryStore()
    issues = _Issues(_EPIC_BODY)
    async with _console(store, issues=issues, default_repo="acme/app", gateway=_Gw("x")) as c:
        assert (await c.post("/issues/66/breakdown", json={})).status_code == 401
        assert (await c.post("/issues/66/breakdown/apply", json={})).status_code == 401
