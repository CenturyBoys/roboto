"""Fluxo refino -> outbox: Telegram (texto/áudio) vira rascunho e enfileira a criação da issue.

Junta agente (refiner), núcleo (Store/outbox) e canais. Determinístico dadas as portas:
1. cria o run do refiner de forma **idempotente** (chave = canal+message_id -> dedup de updates);
2. refina (áudio -> STT -> rascunho);
3. na sequência do estado, enfileira os efeitos ``create_issue`` + ``telegram_notify`` (outbox, D9).
O outbox worker (RouterPublisher) materializa a issue e manda o ack depois (gravar->commit->efeito).
"""

from __future__ import annotations

from datetime import datetime

from roboto.agents.refiner import handle_inbound
from roboto.agents.review import check_issue_readiness, review_issue_semantics
from roboto.app.metering import MeteredGateway
from roboto.channels.model import InboundMessage
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import Error, GithubEvent, Run, RunState
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

    await store.set_state(run.id, RunState.VERIFYING, now)
    await store.enqueue_effect(
        msg.tenant,
        run.id,
        "create_issue",
        {"repo": repo, "title": draft.title, "body": draft.body},
        f"issue:{run.id}",
        now,
    )
    await store.enqueue_effect(
        msg.tenant,
        run.id,
        "telegram_notify",
        {"chat_id": msg.chat_id, "text": refined.value.ack.text},
        f"ack:{run.id}",
        now,
    )
    return Ok(run)
