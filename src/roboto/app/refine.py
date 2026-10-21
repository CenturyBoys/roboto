"""Refino CONVERSACIONAL (D30 + Inc 2): Telegram vira conversa -> rascunho -> proposta -> OK.

Determinístico dadas as portas:
1. a 1ª mensagem abre uma CONVERSA (run do refiner, idempotente por canal+message_id);
2. o entrevistador (``converse``) decide a cada turno: PERGUNTA (falta info) ou PROPÕE o rascunho;
3. perguntas/propostas viram ``telegram_question`` no outbox (o publisher guarda o message_id p/
   roteio por reply, D24); a conversa continua quando o humano responde (em reply) à pergunta;
4. no rascunho pronto -> passa pelos gates (DoR estrutural + juiz semântico) -> PROPÕE (APPROVAL);
5. o fleet NÃO cria issue sozinho — só o "ok" no reply materializa (ver ``inbound``).
"""

from __future__ import annotations

from datetime import datetime

from roboto.agents.refiner import IssueDraft, converse
from roboto.agents.review import check_issue_readiness, review_issue_semantics
from roboto.app.metering import MeteredGateway
from roboto.channels.model import InboundMessage, MessageKind
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import Error, GithubEvent, InteractionKind, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result

_SEED = "IDEIA_INICIAL"  # marcador da interação-semente (guarda a 1ª ideia na trilha da conversa)


async def refine_to_issue(
    msg: InboundMessage,
    *,
    repo: str,
    gateway: ModelGateway,
    transcriber: Transcriber,
    store: Store,
    now: datetime,
) -> Result[Run, Error]:
    """1ª mensagem de uma ideia: abre a conversa de refino (semente) e dá o 1º passo."""
    key = f"tg:conv:{msg.tenant}:{msg.chat_id}:{msg.message_id or 'x'}"
    event = GithubEvent(
        tenant=msg.tenant,
        repo=repo,
        issue_id=f"conv:{msg.chat_id}:{msg.message_id}",
        agent="refiner",
        idempotency_key=key,
        origin_chat_id=msg.chat_id,
    )
    run, created = await store.insert_run_if_absent(event, now)
    if not created:
        return Ok(run)  # update duplicado do Telegram -> não reprocessa

    text = await _resolve_text(msg, transcriber)
    if isinstance(text, Err):
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(text.error)
    if not text.value.strip():
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(Error("invalid", "mensagem vazia"))

    # semente: guarda a ideia inicial como interação respondida (vira o início do transcript)
    seed = await store.create_interaction(
        msg.tenant, run.id, InteractionKind.QUESTION, _SEED, [], now
    )
    await store.answer_interaction(seed.id, text.value, msg.user_id, now)

    metered = MeteredGateway(gateway, store, tenant=msg.tenant, run_id=run.id, now=now)
    return await _ask_or_propose(run, [("user", text.value)], chat_id=msg.chat_id, store=store,
                                 gateway=metered, now=now)


async def discuss_issue(
    msg: InboundMessage, *, repo: str, number: int, title: str, body: str,
    store: Store, now: datetime,
) -> Result[Run, Error]:
    """Fala sobre issue que JÁ existe (D30): ABRE trazendo os detalhes dela (determinístico) e
    pergunta o que o humano quer; a conversa segue no reply -> propõe edição com o OK."""
    key = f"tg:discuss:{msg.tenant}:{msg.chat_id}:{number}:{msg.message_id or 'x'}"
    event = GithubEvent(
        tenant=msg.tenant, repo=repo, issue_id=str(number), agent="refiner",
        idempotency_key=key, origin_chat_id=msg.chat_id,
    )
    run, created = await store.insert_run_if_absent(event, now)
    if not created:
        return Ok(run)

    # semente: contexto da issue + pedido (fica no transcript p/ a conversa a jusante)
    seed_text = (
        f"[Issue #{number} EXISTENTE — ajustar, nunca criar outra]\n"
        f"TÍTULO: {title}\n{body}\n\n[Pedido do humano]: {msg.text}"
    )
    seed = await store.create_interaction(
        msg.tenant, run.id, InteractionKind.QUESTION, _SEED, [], now
    )
    await store.answer_interaction(seed.id, seed_text, msg.user_id, now)

    # abertura DETERMINÍSTICA: traz os detalhes fiéis (sem LLM, sem alucinar) e pergunta a intenção
    opening = _issue_opening(number, title, body)
    inter = await store.create_interaction(
        msg.tenant, run.id, InteractionKind.QUESTION, opening, [], now
    )
    await _enqueue_question(store, run, msg.chat_id, opening, inter.id, f"open:{run.id}", now)
    return Ok(run)


def _issue_opening(number: int, title: str, body: str) -> str:
    excerpt = body.strip()
    if len(excerpt) > 500:
        excerpt = excerpt[:500] + "…"
    return (
        f"📋 *Issue #{number}: {title}*\n\n{excerpt}\n\n"
        "O que você quer? Me diz o que *entender* ou *ajustar* (eu proponho a edição, você "
        f"aprova), ou manda *pega #{number}* pra eu implementar."
    )


async def continue_conversation(
    run: Run, msg: InboundMessage, *, gateway: ModelGateway, store: Store, now: datetime
) -> Result[Run, Error]:
    """Humano respondeu (reply) a uma pergunta da conversa de refino: dá o próximo passo."""
    transcript = await _transcript(store, run.id)
    metered = MeteredGateway(gateway, store, tenant=run.tenant, run_id=run.id, now=now)
    return await _ask_or_propose(run, transcript, chat_id=msg.chat_id, store=store,
                                 gateway=metered, now=now)


async def _ask_or_propose(
    run: Run, transcript: list[tuple[str, str]], *, chat_id: str,
    store: Store, gateway: ModelGateway, now: datetime,
) -> Result[Run, Error]:
    step = await converse(transcript, gateway)
    if isinstance(step, Err):
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(step.error)
    draft, question = step.value.draft, step.value.question

    if draft is not None:  # entrevistador achou que já dá -> ainda passa pelos gates (segurança)
        verdict = check_issue_readiness(draft)
        if not verdict.ready:
            question = f"Quase lá — ainda falta: {', '.join(verdict.missing)}. Me completa?"
            draft = None
        else:
            semantic = await review_issue_semantics(draft, gateway)
            if isinstance(semantic, Ok) and not semantic.value.approved:
                probs = ", ".join(semantic.value.issues) or "detalhar melhor"
                question = f"Pra ficar acionável preciso ajustar: {probs}. Como fica?"
                draft = None

    if draft is not None:  # PROPÕE (D30): só cria com o OK humano
        interaction = await store.create_interaction(
            run.tenant, run.id, InteractionKind.APPROVAL,
            _proposal_text(draft), [draft.title, draft.body], now,
        )
        await _enqueue_question(store, run, chat_id, _proposal_text(draft),
                                interaction.id, f"approve:{interaction.id}", now)
        return Ok(run)

    # PERGUNTA: falta info -> cria interação (reply roteia a resposta) e pergunta no Telegram
    q = question or "Me dá mais detalhes pra eu montar a issue?"
    interaction = await store.create_interaction(
        run.tenant, run.id, InteractionKind.QUESTION, q, [], now
    )
    await _enqueue_question(store, run, chat_id, q, interaction.id, f"ask:{interaction.id}", now)
    return Ok(run)


async def _enqueue_question(
    store: Store, run: Run, chat_id: str, text: str, interaction_id: int,
    dedup: str, now: datetime,
) -> None:
    await store.set_state(run.id, RunState.WAITING, now)  # AWAITING_HUMAN
    await store.enqueue_effect(
        run.tenant, run.id, "telegram_question",
        {"chat_id": chat_id, "text": text, "interaction_id": interaction_id}, dedup, now,
    )


async def _transcript(store: Store, run_id: int) -> list[tuple[str, str]]:
    """Reconstrói o histórico da conversa a partir das interações QUESTION (semente + Q/A)."""
    out: list[tuple[str, str]] = []
    for it in await store.interactions_for_execution(run_id):
        if it.kind is not InteractionKind.QUESTION:
            continue
        if it.prompt == _SEED:
            out.append(("user", it.answer or ""))
        else:
            out.append(("assistant", it.prompt))
            if it.answer:
                out.append(("user", it.answer))
    return out


async def _resolve_text(msg: InboundMessage, transcriber: Transcriber) -> Result[str, Error]:
    if msg.kind is MessageKind.AUDIO:
        if msg.audio is None:
            return Err(Error("invalid", "mensagem de áudio sem bytes"))
        return await transcriber.transcribe(msg.audio, msg.audio_name or "audio.ogg")
    return Ok(msg.text)


def _proposal_text(draft: IssueDraft) -> str:
    body = draft.body.strip()
    if len(body) > 600:
        body = body[:600] + "…"
    return (
        f"📋 Proponho criar esta issue:\n\n*{draft.title}*\n\n{body}\n\n"
        "Responde em *reply* com *ok* que eu crio — ou diga o que ajustar "
        "(não crio nada sem o seu ok)."
    )
