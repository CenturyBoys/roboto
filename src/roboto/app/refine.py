"""Fluxo refino -> outbox: Telegram (texto/áudio) vira rascunho e enfileira a criação da issue.

Junta agente (refiner), núcleo (Store/outbox) e canais. Determinístico dadas as portas:
1. cria o run do refiner de forma **idempotente** (chave = canal+message_id -> dedup de updates);
2. refina (áudio -> STT -> rascunho);
3. na sequência do estado, enfileira os efeitos ``create_issue`` + ``telegram_notify`` (outbox, D9).
O outbox worker (RouterPublisher) materializa a issue e manda o ack depois (gravar->commit->efeito).
"""

from __future__ import annotations

from datetime import datetime

from roboto.agents.refiner import IssueDraft, handle_inbound
from roboto.agents.review import check_issue_readiness, review_issue_semantics
from roboto.app.metering import MeteredGateway
from roboto.channels.model import InboundMessage
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import Error, GithubEvent, InteractionKind, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result


async def refine_to_issue(
    msg: InboundMessage,
    *,
    repo: str,
    gateway: ModelGateway,
    transcriber: Transcriber,
    store: Store,
    now: datetime,
) -> Result[Run, Error]:
    key = f"tg:{msg.tenant}:{msg.message_id or msg.chat_id}"
    event = GithubEvent(
        tenant=msg.tenant,
        repo=repo,
        issue_id=f"refine:{msg.chat_id}:{msg.message_id}",
        agent="refiner",
        idempotency_key=key,
    )
    run, created = await store.insert_run_if_absent(event, now)
    if not created:
        return Ok(run)  # update duplicado do Telegram -> não reprocessa

    metered = MeteredGateway(gateway, store, tenant=msg.tenant, run_id=run.id, now=now)
    refined = await handle_inbound(msg, metered, transcriber)
    if isinstance(refined, Err):
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(refined.error)

    draft = refined.value.draft

    # gate de prontidão (DoR) ANTES de criar a issue — nada vira dev sem issue completa (D28)
    verdict = check_issue_readiness(draft)
    if not verdict.ready:
        await store.set_state(run.id, RunState.WAITING, now)
        falta = ", ".join(verdict.missing)
        text = f"Issue incompleta — falta: {falta}. Reenvie com mais detalhes."
        await store.enqueue_effect(
            msg.tenant,
            run.id,
            "telegram_notify",
            {"chat_id": msg.chat_id, "text": text},
            f"incompleta:{run.id}",
            now,
        )
        return Ok(run)

    # gate SEMÂNTICO (juiz): pega issue estruturalmente ok mas sem sentido (ex.: vinda de "ola").
    semantic = await review_issue_semantics(draft, metered)
    if isinstance(semantic, Ok) and not semantic.value.approved:
        await store.set_state(run.id, RunState.WAITING, now)
        probs = ", ".join(semantic.value.issues) or "sem detalhes"
        text = f"Issue precisa de ajuste — {probs}. Reenvie com mais contexto."
        await store.enqueue_effect(
            msg.tenant,
            run.id,
            "telegram_notify",
            {"chat_id": msg.chat_id, "text": text},
            f"review:{run.id}",
            now,
        )
        return Ok(run)

    # D30: o fleet NÃO cria issue sozinho — PROPÕE o rascunho e espera o OK humano (reply) p/ criar.
    # O rascunho fica em options=[title, body] da interação; o "ok" no reply materializa a issue.
    interaction = await store.create_interaction(
        msg.tenant, run.id, InteractionKind.APPROVAL,
        _proposal_text(draft), [draft.title, draft.body], now,
    )
    await store.set_state(run.id, RunState.WAITING, now)  # AWAITING_HUMAN
    await store.enqueue_effect(
        msg.tenant,
        run.id,
        "telegram_question",
        {"chat_id": msg.chat_id, "text": _proposal_text(draft),
         "interaction_id": interaction.id},
        f"approve:{interaction.id}",
        now,
    )
    return Ok(run)


def _proposal_text(draft: IssueDraft) -> str:
    body = draft.body.strip()
    if len(body) > 600:
        body = body[:600] + "…"
    return (
        f"📋 Proponho criar esta issue:\n\n*{draft.title}*\n\n{body}\n\n"
        "Responde em *reply* com *ok* que eu crio — ou diga o que ajustar "
        "(não crio nada sem o seu ok)."
    )
