"""Laços periódicos que dão "pernas" ao sistema (D3): poll do canal, outbox worker, sweeper.

`run_periodic` é o laço genérico (para limpo via `asyncio.Event`); os ticks são funções puras já
testadas (`publish_outbox`, `sweep`) ou `poll_tick` (drena o canal e despacha). Um tick que falha
não derruba o laço.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from roboto.app.inbound import InboundOutcome, dispatch_inbound
from roboto.channels.model import OutboundMessage
from roboto.channels.port import Channel
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok

_CLARIFY = "Não localizei a pergunta — responda em *reply* à mensagem da decisão."


async def run_periodic(
    tick: Callable[[], Awaitable[object]], interval: float, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            await tick()
        except Exception:  # resiliência: um tick com erro não mata o laço
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


async def poll_tick(
    channel: Channel,
    store: Store,
    *,
    repo: str,
    gateway: ModelGateway,
    transcriber: Transcriber,
    now: Callable[[], datetime],
) -> None:
    polled = await channel.poll()
    if isinstance(polled, Err):
        return
    for msg in polled.value:
        outcome = await dispatch_inbound(
            msg, repo=repo, gateway=gateway, transcriber=transcriber, store=store, now=now()
        )
        if isinstance(outcome, Ok) and outcome.value is InboundOutcome.UNROUTED:
            await channel.send(OutboundMessage(chat_id=msg.chat_id, text=_CLARIFY))
