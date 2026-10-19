"""Interação humana (D24): request_human_input + roteamento de reply + captura de message_id."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from roboto.app.effects import TelegramQuestionPublisher
from roboto.app.human import handle_reply, request_human_input
from roboto.channels.model import InboundMessage, MessageKind
from roboto.channels.telegram import TelegramChannel
from roboto.orchestrator.model import (
    GithubEvent,
    InteractionKind,
    InteractionStatus,
    RunState,
)
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _reply(text: str, to: str | None, user: str = "u1") -> InboundMessage:
    return InboundMessage(
        tenant="acme",
        chat_id="5",
        user_id=user,
        kind=MessageKind.TEXT,
        text=text,
        message_id="200",
        reply_to_message_id=to,
    )


async def _run(store: InMemoryStore) -> int:
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="1", agent="impl", idempotency_key="k"
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    return run.id


async def test_request_human_input_waits_and_enqueues_question() -> None:
    store = InMemoryStore()
    execution_id = await _run(store)
    result = await request_human_input(
        store,
        tenant="acme",
        execution_id=execution_id,
        chat_id="5",
        kind=InteractionKind.DECISION,
        prompt="Redis ou DB?",
        options=["Redis", "DB"],
        now=_T0,
    )
    assert isinstance(result, Ok)
    assert store._runs[execution_id].state is RunState.WAITING  # AWAITING_HUMAN
    effects = await store.pending_effects(10)
    assert len(effects) == 1
    assert effects[0].kind == "telegram_question"
    assert "1. Redis" in effects[0].payload["text"]
    assert f"Q-{result.value.id}" in effects[0].payload["text"]


async def test_question_publisher_captures_message_id_for_routing() -> None:
    store = InMemoryStore()
    execution_id = await _run(store)
    requested = await request_human_input(
        store,
        tenant="acme",
        execution_id=execution_id,
        chat_id="5",
        kind=InteractionKind.QUESTION,
        prompt="qual?",
        options=[],
        now=_T0,
    )
    assert isinstance(requested, Ok)
    effect = (await store.pending_effects(10))[0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 777}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        pub = TelegramQuestionPublisher(
            TelegramChannel("tok", "acme", allowlist=set(), client=client), store
        )
        assert isinstance(await pub.send(effect), Ok)
    finally:
        await client.aclose()

    # agora a resposta em reply à msg 777 roteia para a interação certa
    found = await store.get_interaction_by_message_id("acme", "777")
    assert found is not None
    assert found.id == requested.value.id


async def test_handle_reply_routes_and_first_wins() -> None:
    store = InMemoryStore()
    execution_id = await _run(store)
    requested = await request_human_input(
        store,
        tenant="acme",
        execution_id=execution_id,
        chat_id="5",
        kind=InteractionKind.DECISION,
        prompt="?",
        options=["a", "b"],
        now=_T0,
    )
    assert isinstance(requested, Ok)
    await store.set_interaction_message_id(requested.value.id, "777")

    # reply correto -> aceita
    first = await handle_reply(store, _reply("2, com abstração", to="777"), _T0)
    assert isinstance(first, Ok)
    assert first.value.matched is True
    assert first.value.accepted is True
    assert store._interactions[requested.value.id].status is InteractionStatus.ANSWERED

    # segundo respondente -> casa mas é rejeitado (decisão não muda)
    second = await handle_reply(store, _reply("1", to="777", user="u2"), _T0)
    assert isinstance(second, Ok)
    assert second.value.matched is True
    assert second.value.accepted is False
    assert store._interactions[requested.value.id].answer == "2, com abstração"


async def test_handle_reply_non_reply_and_unknown_are_unmatched() -> None:
    store = InMemoryStore()
    # sem reply
    nonreply = await handle_reply(store, _reply("oi", to=None), _T0)
    assert isinstance(nonreply, Ok)
    assert nonreply.value.matched is False
    # reply a mensagem desconhecida -> não casa (chamador pede esclarecimento)
    unknown = await handle_reply(store, _reply("2", to="999"), _T0)
    assert isinstance(unknown, Ok)
    assert unknown.value.matched is False
