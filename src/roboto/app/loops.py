"""Laços periódicos que dão "pernas" ao sistema (D3): poll do canal, outbox worker, sweeper.

`run_periodic` é o laço genérico (para limpo via `asyncio.Event`); os ticks são funções puras já
testadas (`publish_outbox`, `sweep`) ou `poll_tick` (drena o canal e despacha). Um tick que falha
não derruba o laço.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from roboto.app.engine_loop import drive_turn
from roboto.app.inbound import IssueLister, dispatch_inbound
from roboto.channels.model import OutboundMessage
from roboto.channels.port import Channel
from roboto.engines.port import CodingEngine
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok


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


async def process_run_tick(
    engine: CodingEngine,
    store: Store,
    *,
    tenant: str,
    chat_id: str,
    now: Callable[[], datetime],
    lease_seconds: int = 300,
) -> None:
    """Pega o próximo run da fila e dispara o motor de coding (D22). Fila vazia = no-op."""
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds)
    if run is None:
        return
    await drive_turn(engine, store, run=run, chat_id=chat_id, now=moment)


async def poll_tick(
    channel: Channel,
    store: Store,
    *,
    repo: str,
    gateway: ModelGateway,
    transcriber: Transcriber,
    now: Callable[[], datetime],
    github: IssueLister | None = None,
    tenant: str | None = None,
    engine_scope: bool = False,
) -> None:
    # retoma o cursor persistido (D30): no restart não relê mensagens já processadas
    if tenant is not None:
        saved = await store.get_channel_offset(tenant, "telegram")
        if saved is not None:
            channel.cursor = str(saved)
    polled = await channel.poll()
    if isinstance(polled, Err):
        return
    for msg in polled.value:
        result = await dispatch_inbound(
            msg, repo=repo, gateway=gateway, transcriber=transcriber,
            store=store, now=now(), github=github, engine_scope=engine_scope,
        )
        if isinstance(result, Ok) and result.value.reply:
            await channel.send(OutboundMessage(chat_id=msg.chat_id, text=result.value.reply))
    if tenant is not None and channel.cursor is not None:
        await store.set_channel_offset(tenant, "telegram", int(channel.cursor), now())
