"""Processa o inbound do Telegram ao vivo (one-shot): poll -> dispatch -> responde + publica efeitos.

Idéia nova -> refino + gate DoR -> cria issue no GitHub + ack. Comando (issues/pega) -> responde.
Usa OpenRouter (refino/review) + GitHub App (PAT) + Telegram reais; NÃO precisa de ccr/engine.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from roboto.app.compose import build_adapters
from roboto.app.inbound import dispatch_inbound
from roboto.channels.model import OutboundMessage
from roboto.config import load_config
from roboto.orchestrator.core import publish_outbox
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok


async def main() -> int:
    loaded = load_config(os.environ)
    if isinstance(loaded, Err):
        print("config inválida:", loaded.error.message)
        return 1
    config = loaded.value
    store = InMemoryStore()
    adapters = build_adapters(config, store)
    now = datetime(2026, 1, 1, tzinfo=UTC) if os.environ.get("ROBOTO_FIXED_NOW") else datetime.now(UTC)

    polled = await adapters.channel.poll()
    if isinstance(polled, Err):
        print("poll falhou:", polled.error.message)
        return 1
    print(f"[tg] {len(polled.value)} mensagem(ns)")
    for msg in polled.value:
        res = await dispatch_inbound(
            msg, repo=config.default_repo, gateway=adapters.gateway,
            transcriber=adapters.transcriber, store=store, now=now, github=adapters.github,
        )
        if isinstance(res, Err):
            print(f"  {msg.text!r} -> ERRO: {res.error.message}")
            continue
        print(f"  {msg.text!r} -> {res.value.outcome}")
        if res.value.reply:
            await adapters.channel.send(OutboundMessage(chat_id=msg.chat_id, text=res.value.reply))

    published = await publish_outbox(store, adapters.router, now)
    n = published.value if isinstance(published, Ok) else 0
    print(f"[tg] efeitos publicados (issue/ack/pergunta): {n}")
    calls = await store.llm_calls(config.tenant, 50)
    tok = sum(c.tokens_in + c.tokens_out for c in calls)
    print(f"[tg] llm_calls={len(calls)} tokens={tok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
