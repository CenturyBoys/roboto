"""Laços: run_periodic para limpo via Event; poll_tick despacha e esclarece não-roteados."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from roboto.app.loops import poll_tick, run_periodic
from roboto.channels.model import InboundMessage, MessageKind, OutboundMessage
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def test_run_periodic_stops_after_ticks() -> None:
    stop = asyncio.Event()
    count = {"n": 0}

    async def tick() -> None:
        count["n"] += 1
        if count["n"] >= 3:
            stop.set()

    await run_periodic(tick, 0.0, stop)
    assert count["n"] == 3


async def test_run_periodic_survives_failing_tick() -> None:
    stop = asyncio.Event()
    count = {"n": 0}

    async def tick() -> None:
        count["n"] += 1
        if count["n"] >= 2:
            stop.set()
            return
        raise RuntimeError("boom")  # não deve derrubar o laço

    await run_periodic(tick, 0.0, stop)
    assert count["n"] == 2


class _FakeChannel:
    def __init__(self, msgs: list[InboundMessage]) -> None:
        self._msgs = msgs
        self.sent: list[OutboundMessage] = []

    async def poll(self) -> Ok[list[InboundMessage]]:
        return Ok(self._msgs)

    async def send(self, msg: OutboundMessage) -> Ok[str]:
        self.sent.append(msg)
        return Ok("1")


async def test_poll_tick_refines_new_and_clarifies_unrouted() -> None:
    store = InMemoryStore()
    msgs = [
        InboundMessage(
            tenant="acme", chat_id="5", user_id="u1", kind=MessageKind.TEXT,
            text="nova feature", message_id="1",
        ),
        InboundMessage(
            tenant="acme", chat_id="6", user_id="u1", kind=MessageKind.TEXT,
            text="1", message_id="2", reply_to_message_id="999",
        ),
    ]
    channel = _FakeChannel(msgs)
    await poll_tick(
        channel, store, repo="acme/app",
        gateway=StubModelGateway(), transcriber=StubTranscriber(), now=lambda: _T0,
    )
    # 1ª mensagem -> refino (2 efeitos no outbox); 2ª -> reply desconhecido -> esclarecimento
    assert len(await store.pending_effects(10)) == 2
    assert len(channel.sent) == 1
    assert "reply" in channel.sent[0].text
