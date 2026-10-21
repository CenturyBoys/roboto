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
from roboto.app.refine import continue_conversation, discuss_issue, refine_to_issue, start_scope
from roboto.channels.model import InboundMessage
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import Error, GithubEvent, Interaction, InteractionKind, RunState
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result


class InboundOutcome(StrEnum):
    ANSWERED = "answered"  # reply roteou e respondeu uma interação
    UNROUTED = "unrouted"  # reply a algo desconhecido -> pedir esclarecimento
    REFINED = "refined"  # mensagem nova -> rascunho de issue PROPOSTO (aguarda OK, D30)
    PICKED = "picked"  # operador pegou/atribuiu uma issue ao fleet
    LISTED = "listed"  # operador listou issues abertas
    CREATED = "created"  # humano aprovou o rascunho (reply ok) -> issue enfileirada
    DECLINED = "declined"  # humano não aprovou o rascunho -> descartado
    EDITED = "edited"  # humano aprovou EDIÇÃO de issue existente -> update enfileirado
    DISCUSSING = "discussing"  # conversa sobre issue existente aberta
    REMEMBERED = "remembered"  # fato gravado no second brain (trilha G)


class IssueLister(Protocol):
    async def list_open_issues(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str]], Error]: ...

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]: ...


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
    engine_scope: bool = False,
) -> Result[InboundResult, Error]:
    command = parse_command(msg.text)
    if command is not None:
        return await _run_command(
            command, msg, repo=repo, store=store, now=now, github=github
        )

    if msg.reply_to_message_id:
        reply = await handle_reply(store, msg, now)
        if isinstance(reply, Err):
            return Err(reply.error)
        if reply.value.matched:
            inter = reply.value.interaction
            if reply.value.accepted and inter is not None:
                if inter.kind is InteractionKind.APPROVAL:
                    return await _resolve_issue_approval(inter, msg, store=store, now=now)
                if inter.kind is InteractionKind.QUESTION:
                    run = await store.get_run(inter.execution_id)
                    if run is not None and run.agent == "refiner":  # conversa de refino (Inc 2)
                        cont = await continue_conversation(
                            run, msg, gateway=gateway, store=store, now=now
                        )
                        if isinstance(cont, Err):
                            return Err(cont.error)
                        return Ok(InboundResult(InboundOutcome.REFINED))
            return Ok(InboundResult(InboundOutcome.ANSWERED))
        clar = "Não localizei a pergunta — responda em *reply* à mensagem da decisão."
        return Ok(InboundResult(InboundOutcome.UNROUTED, clar))

    if engine_scope:  # ideia nova + motor disponível -> o Claude escaneia o repo e monta a issue
        scoped = await start_scope(msg, repo=repo, transcriber=transcriber, store=store, now=now)
        if isinstance(scoped, Err):
            return Err(scoped.error)
        return Ok(InboundResult(InboundOutcome.REFINED))
    refined = await refine_to_issue(
        msg, repo=repo, gateway=gateway, transcriber=transcriber, store=store, now=now
    )
    if isinstance(refined, Err):
        return Err(refined.error)
    return Ok(InboundResult(InboundOutcome.REFINED))


_HELP_TEXT = (
    "⚡ *Potter* — como falar comigo:\n\n"
    "💡 *Ideia nova* (vira issue)\n"
    "   ex.: \"quero um placar de vitórias por jogador\"\n"
    "   eu entrevisto, proponho a issue e só crio com seu *ok*.\n\n"
    "📋 *Falar de uma issue que já existe*\n"
    "   ex.: \"sobre a #180\" · \"a #180 precisa cobrir X\"\n"
    "   eu busco a issue e converso sobre ela; edito só com seu *ok*.\n\n"
    "🔎 *Listar*\n"
    "   \"issues\" · \"qual issue dá pra fazer\"\n\n"
    "🛠️ *Trabalhar / implementar*\n"
    "   \"pega #180\" — checo o DoR; se faltar, te peço aqui.\n\n"
    "Regras: responda minhas perguntas em *reply*; eu nunca crio/edito/mergeio "
    "sem seu *ok*. Mande \"ajuda\" pra ver isso de novo."
)

_AFFIRM = {
    "ok", "okay", "sim", "pode", "cria", "criar", "blz", "beleza", "yes", "y",
    "s", "manda", "vai", "isso", "👍", "confirmo", "confirmar",
}


async def _resolve_issue_approval(
    inter: Interaction, msg: InboundMessage, *, store: Store, now: datetime
) -> Result[InboundResult, Error]:
    """Humano respondeu à PROPOSTA de issue (D30): 'ok' cria; qualquer outra coisa descarta."""
    run = await store.get_run(inter.execution_id)
    if run is None:
        return Ok(InboundResult(InboundOutcome.ANSWERED))
    first = msg.text.strip().lower().split()[0].strip(".,!?") if msg.text.strip() else ""
    if first not in _AFFIRM:
        await store.set_state(run.id, RunState.ABANDONED, now)
        return Ok(InboundResult(
            InboundOutcome.DECLINED,
            "Beleza, não criei. Me manda a ideia ajustada que eu reproponho.",
        ))
    title = inter.options[0] if inter.options else "(sem título)"
    body = inter.options[1] if len(inter.options) > 1 else ""
    await store.set_state(run.id, RunState.VERIFYING, now)
    if run.issue_id.isdigit():  # EDIÇÃO de issue existente (discuss) — D30: corpo + trilha
        note = f"Editado via Telegram a pedido do operador (chat {msg.chat_id})."
        await store.enqueue_effect(
            run.tenant, run.id, "update_issue",
            {"repo": run.repo, "number": run.issue_id, "title": title, "body": body, "note": note},
            f"update:{run.id}", now,
        )
        await store.enqueue_effect(
            run.tenant, run.id, "telegram_notify",
            {"chat_id": msg.chat_id, "text": f"✅ Issue #{run.issue_id} atualizada."},
            f"ack:{run.id}", now,
        )
        return Ok(InboundResult(InboundOutcome.EDITED))
    await store.enqueue_effect(  # CRIAÇÃO de issue nova
        run.tenant, run.id, "create_issue",
        {"repo": run.repo, "title": title, "body": body}, f"issue:{run.id}", now,
    )
    await store.enqueue_effect(
        run.tenant, run.id, "telegram_notify",
        {"chat_id": msg.chat_id, "text": f"✅ Issue criada: {title}"}, f"ack:{run.id}", now,
    )
    return Ok(InboundResult(InboundOutcome.CREATED))


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
    if kind == "help":
        return Ok(InboundResult(InboundOutcome.LISTED, _HELP_TEXT))

    if kind == "remember":  # second brain (trilha G): grava um fato do projeto
        await store.remember(msg.tenant, arg, kind="fato", ref="", now=now)
        return Ok(InboundResult(InboundOutcome.REMEMBERED, "🧠 Anotado na memória do projeto."))

    if kind == "discuss":  # falar sobre issue que já existe -> busca e conversa SOBRE ela (D30)
        if github is None:
            return Ok(InboundResult(InboundOutcome.ANSWERED, "Não consigo acessar as issues."))
        got = await github.get_issue(repo, int(arg))
        if isinstance(got, Err):
            return Ok(InboundResult(InboundOutcome.ANSWERED, f"Não achei a issue #{arg}."))
        title, body = got.value
        disc = await discuss_issue(
            msg, repo=repo, number=int(arg), title=title, body=body, store=store, now=now,
        )
        if isinstance(disc, Err):
            return Err(disc.error)
        return Ok(InboundResult(InboundOutcome.DISCUSSING))

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
