"""Interação humana (D24): request_human_input + roteamento de resposta por reply.

Fluxo (§4/§6 da Trilha N):
- `request_human_input`: cria a `interaction` (pending), coloca a execução em `WAITING`
  (AWAITING_HUMAN — sobrevive a restart) e enfileira a pergunta no **outbox**
  (`telegram_question`); o publisher guarda o `message_id` do canal na interação.
- `handle_reply`: uma mensagem em *reply* localiza a interação pelo `message_id` (nunca por
  inferência do texto), valida e registra a resposta (**1ª válida vence**; destino desconhecido →
  não casa, o chamador pede esclarecimento). Retomar a execução (WAITING->RUNNING) é do motor (D22).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from roboto.channels.model import InboundMessage
from roboto.orchestrator.model import Error, Interaction, InteractionKind, RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result


@dataclass(frozen=True)
class ReplyOutcome:
    matched: bool  # era reply a uma interação conhecida?
    accepted: bool  # a resposta foi aceita (1ª válida)?
    interaction: Interaction | None


def format_question(prompt: str, options: list[str], interaction: Interaction) -> str:
    lines = [prompt]
    if options:
        lines.append("")
        lines.extend(f"{i}. {opt}" for i, opt in enumerate(options, start=1))
    lines.append("")
    lines.append(f"Execução: E-{interaction.execution_id} · Interação: Q-{interaction.id}")
    return "\n".join(lines)


async def request_human_input(
    store: Store,
    *,
    tenant: str,
    execution_id: int,
    chat_id: str,
    kind: InteractionKind,
    prompt: str,
    options: list[str],
    now: datetime,
    session_id: int | None = None,
    expires_at: datetime | None = None,
) -> Result[Interaction, Error]:
    interaction = await store.create_interaction(
        tenant, execution_id, kind, prompt, options, now, session_id, expires_at
    )
    await store.set_state(execution_id, RunState.WAITING, now)  # AWAITING_HUMAN
    await store.enqueue_effect(
        tenant,
        execution_id,
        "telegram_question",
        {"chat_id": chat_id, "text": format_question(prompt, options, interaction),
         "interaction_id": interaction.id},
        f"question:{interaction.id}",
        now,
    )
    return Ok(interaction)


async def handle_reply(
    store: Store, msg: InboundMessage, now: datetime
) -> Result[ReplyOutcome, Error]:
    if not msg.reply_to_message_id:
        return Ok(ReplyOutcome(matched=False, accepted=False, interaction=None))
    interaction = await store.get_interaction_by_message_id(
        msg.tenant, msg.reply_to_message_id
    )
    if interaction is None:
        return Ok(ReplyOutcome(matched=False, accepted=False, interaction=None))
    accepted = await store.answer_interaction(interaction.id, msg.text, msg.user_id, now)
    return Ok(ReplyOutcome(matched=True, accepted=accepted, interaction=interaction))
