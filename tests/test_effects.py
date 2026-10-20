"""Roteamento do outbox por kind + caminho ponta-a-ponta (refino -> issue + ack)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from roboto.app.effects import GithubIssuePublisher, TelegramPublisher
from roboto.app.refine import refine_to_issue
from roboto.channels.model import InboundMessage, MessageKind
from roboto.channels.telegram import TelegramChannel
from roboto.github.app import GithubAppClient
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.core import publish_outbox
from roboto.orchestrator.model import OutboxItem
from roboto.orchestrator.runner import RouterPublisher
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def test_router_unknown_kind_is_err() -> None:
    item = OutboxItem(
        id=1,
        tenant="acme",
        run_id=1,
        kind="mystery",
        payload={},
        dedup_key="d",
        status="pending",
        created_at=_T0,
    )
    result = await RouterPublisher({}).send(item)
    assert isinstance(result, Err)
    assert result.error.kind == "effect"


async def test_outbox_materializes_issue_and_notifies() -> None:
    store = InMemoryStore()
    msg = InboundMessage(
        tenant="acme",
        chat_id="5",
        user_id="u1",
        kind=MessageKind.TEXT,
        text="arruma o login",
        message_id="11",
    )
    await refine_to_issue(
        msg,
        repo="acme/app",
        gateway=StubModelGateway(),  # resposta default = issue completa (passa o gate DoR)
        transcriber=StubTranscriber(),
        store=store,
        now=_T0,
    )

    posted = {"issues": 0, "send": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/issues"):
            posted["issues"] += 1
            return httpx.Response(
                201, json={"number": 1, "html_url": "https://github.com/acme/app/issues/1"}
            )
        if path.endswith("/sendMessage"):
            posted["send"] += 1
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        gh = GithubAppClient(
            app_id="1", private_key="", installation_id="1", client=client, token="t"
        )
        ch = TelegramChannel("tok", "acme", allowlist=set(), client=client)
        router = RouterPublisher(
            {"create_issue": GithubIssuePublisher(gh), "telegram_notify": TelegramPublisher(ch)}
        )
        sent = await publish_outbox(store, router, _T0)
        assert isinstance(sent, Ok)
        assert sent.value == 2
        assert posted == {"issues": 1, "send": 1}
        assert await store.pending_effects(10) == []  # tudo marcado como enviado
    finally:
        await client.aclose()
