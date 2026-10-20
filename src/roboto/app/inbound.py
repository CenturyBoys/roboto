"""Dispatch de mensagem inbound: comando do operador, reply a interação, ou nova ideia (refino).

Ordem: (1) comando explícito (`list` issues / `pick <N>` pega issue p/ o fleet); (2) reply a uma
interação (roteia pelo message_id, nunca por inferência); (3) mensagem nova → refino de issue.
Retorna `InboundResult(outcome, reply)` — o `reply` (quando houver) o canal responde no chat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from roboto.app.commands import parse_command
from roboto.app.human import handle_reply
from roboto.app.refine import refine_to_issue
from roboto.channels.model import InboundMessage
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import Error, GithubEvent, RunState
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result


class InboundOutcome(StrEnum):
    ANSWERED = "answered"  # reply roteou e respondeu uma interação
    UNROUTED = "unrouted"  # reply a algo desconhecido -> pedir esclarecimento
    REFINED = "refined"  # mensagem nova -> rascunho de issue enfileirado
    PICKED = "picked"  # operador pegou/atribuiu uma issue ao fleet
    LISTED = "listed"  # operador listou issues abertas


class IssueLister(Protocol):
    async def list_open_issues(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str]], Error]: ...


@dataclass(frozen=True)
class InboundResult:
    outcome: InboundOutcome
    reply: str | None = None  # texto a responder no chat (quando houver)


async def dispatch_inbound(
    msg: InboundMessage,
    *,
    repo: str,
    gateway: ModelGateway,
    transcriber: Transcriber,
    store: Store,
    now: datetime,
    github: IssueLister | None = None,
) -> Result[InboundResult, Error]:
    command = parse_command(msg.text)
    if command is not None:
        return await _run_command(command, msg, repo=repo, store=store, now=now, github=github)

    if msg.reply_to_message_id:
        reply = await handle_reply(store, msg, now)
        if isinstance(reply, Err):
            return Err(reply.error)
        if reply.value.matched:
            return Ok(InboundResult(InboundOutcome.ANSWERED))
        clar = "Não localizei a pergunta — responda em *reply* à mensagem da decisão."
        return Ok(InboundResult(InboundOutcome.UNROUTED, clar))

    refined = await refine_to_issue(
        msg, repo=repo, gateway=gateway, transcriber=transcriber, store=store, now=now
    )
    if isinstance(refined, Err):
        return Err(refined.error)
    return Ok(InboundResult(InboundOutcome.REFINED))


async def _run_command(
    command: tuple[str, str],
    msg: InboundMessage,
    *,
    repo: str,
    store: Store,
    now: datetime,
    github: IssueLister | None,
) -> Result[InboundResult, Error]:
    kind, arg = command
    if kind == "pick":
        event = GithubEvent(
            tenant=msg.tenant,
            repo=repo,
            issue_id=arg,
            agent="impl",
            idempotency_key=f"tg:pick:{msg.tenant}:{arg}",
            origin_chat_id=msg.chat_id,  # feedback do loop volta pra este chat (D30)
        )
        run, created = await store.insert_run_if_absent(event, now)
        if not created and run.state in (RunState.WAITING, RunState.FAILED):
            # re-pegar retoma um run parado (ex.: você completou o DoR) -> volta pra fila
            await store.set_state(run.id, RunState.QUEUED, now)
            reply = f"Retomando a #{arg} — vou checar o DoR de novo e, se completa, trabalhar."
        else:
            reply = f"Ok, peguei a issue #{arg} — vou checar o DoR e, se completa, trabalhar."
        return Ok(InboundResult(InboundOutcome.PICKED, reply))

    # list
    if github is None:
        return Ok(InboundResult(InboundOutcome.LISTED, "Listagem de issues indisponível."))
    listed = await github.list_open_issues(repo)
    if isinstance(listed, Err):
        return Err(listed.error)
    if not listed.value:
        return Ok(InboundResult(InboundOutcome.LISTED, "Nenhuma issue aberta."))
    lines = "\n".join(f"#{n} {t}" for n, t in listed.value)
    return Ok(InboundResult(InboundOutcome.LISTED, f"Issues abertas:\n{lines}"))
