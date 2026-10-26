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

# Marcadores que delimitam o CORPO LIMPO da issue na saída do refino: o motor pode narrar/pensar
# fora deles, mas o "📝 Aplicar na issue" extrai só o que está ENTRE eles (sem preâmbulo).
ISSUE_BODY_START = "===ISSUE-INICIO==="
ISSUE_BODY_END = "===ISSUE-FIM==="


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


async def process_refine_tick(
    engine: CodingEngine,
    store: Store,
    github: IssueLister,
    *,
    tenant: str,
    chat_id: str,
    now: Callable[[], datetime],
    lease_seconds: int = 1800,
) -> None:
    """Refino ENGINE-SCOPED (trilha O, Fatia 6/C): o motor LÊ o repo e propõe a issue fundamentada.

    Pega um run `agent='refine'`, injeta o corpo atual da issue como contexto e roda o motor com um
    prompt read-only (lê o repo, NÃO edita). Os eventos viram feed ao vivo (session_event). Fecha a
    reclamação do refino cego: aqui o agente realmente lê o código (env.ts, usos de X, etc.).
    """
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds, agent="refine")
    if run is None:
        return
    contexto = ""
    if run.issue_id.isdigit():
        got = await github.get_issue(run.repo, int(run.issue_id))
        if isinstance(got, Ok):
            title, body = got.value
            contexto = f"\n\nIssue atual — título: {title}\nCorpo atual:\n{body}"
    prompt = (
        f"Refine a issue #{run.issue_id} do repo {run.repo}.{contexto}\n\n"
        "Seu trabalho é ESCREVER a issue refinada — NÃO executar a tarefa dela. Mesmo que a issue "
        "fale em 'discovery'/'mapear'/'levantar', você NÃO faz o levantamento agora: você descreve "
        "COMO fazê-lo (escopo + critérios). "
        "LIMITE DURO: no máximo ~10 consultas de leitura só pra fundamentar; prefira code-intel "
        "(workspace_symbols/find_references) a Read de arquivo inteiro. NÃO varra o repo. "
        "Atingindo ~10 consultas (ou antes), PARE e EMITA a proposta — terminar com a issue é "
        "OBRIGATÓRIO, mesmo que você não tenha explorado tudo. "
        "NÃO edite arquivos nem abra PR. A proposta DEVE ter as QUATRO seções, nesta ordem e com "
        "estes títulos exatos: `## Contexto`, `## Escopo`, `## Critérios de aceite` (itens "
        "'- [ ]') e `## DoD` (itens '- [ ]'). NUNCA omita o DoD; se faltar info, preencha com o "
        "razoável — mas as quatro seções SEMPRE aparecem.\n\n"
        f"IMPORTANTE: emita o CORPO FINAL da issue — e NADA MAIS — entre as linhas "
        f"`{ISSUE_BODY_START}` e `{ISSUE_BODY_END}`, cada marcador sozinho em sua própria linha. "
        "Dentro dos marcadores vá direto ao markdown da issue (sem 'vou propor', sem comentários, "
        "sem cercas de código). Qualquer explicação sua deve ficar FORA dos marcadores."
    )
    await drive_turn(engine, store, run=run, chat_id=chat_id, now=moment, prompt=prompt)


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
