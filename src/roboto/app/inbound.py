"""Dispatch de mensagem inbound: reply a uma interação vs. nova solicitação de refino.

Regra (Trilha N §4/§6): resposta em *reply* roteia para a interação pelo `message_id` (nunca por
inferência); mensagem nova (sem reply) vira refino de issue. Reply a algo desconhecido = `UNROUTED`
(o chamador pede esclarecimento, não adivinha). Determinístico dadas as portas.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from roboto.app.human import handle_reply
from roboto.app.refine import refine_to_issue
from roboto.channels.model import InboundMessage
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import Error
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result


class InboundOutcome(StrEnum):
    ANSWERED = "answered"  # reply roteou e respondeu uma interação
    UNROUTED = "unrouted"  # reply a algo desconhecido -> pedir esclarecimento
    REFINED = "refined"  # mensagem nova -> rascunho de issue enfileirado


async def dispatch_inbound(
    msg: InboundMessage,
    *,
    repo: str,
    gateway: ModelGateway,
    transcriber: Transcriber,
    store: Store,
    now: datetime,
) -> Result[InboundOutcome, Error]:
    if msg.reply_to_message_id:
        reply = await handle_reply(store, msg, now)
        if isinstance(reply, Err):
            return Err(reply.error)
        return Ok(InboundOutcome.ANSWERED if reply.value.matched else InboundOutcome.UNROUTED)

    refined = await refine_to_issue(
        msg, repo=repo, gateway=gateway, transcriber=transcriber, store=store, now=now
    )
    if isinstance(refined, Err):
        return Err(refined.error)
    return Ok(InboundOutcome.REFINED)
