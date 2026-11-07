"""Laços periódicos que dão "pernas" ao sistema (D3): poll do canal, outbox worker, sweeper.

`run_periodic` é o laço genérico (para limpo via `asyncio.Event`); os ticks são funções puras já
testadas (`publish_outbox`, `sweep`) ou `poll_tick` (drena o canal e despacha). Um tick que falha
não derruba o laço.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import check_issue_readiness
from roboto.app.code_intel_brief import code_intel_brief
from roboto.app.engine_loop import TurnOutcome, drive_turn
from roboto.app.inbound import IssueLister, dispatch_inbound
from roboto.app.memory import recall_block
from roboto.app.related_issues import related_issues_block
from roboto.app.repo_profile import read_agents_conventions
from roboto.app.web_research import research_block, research_is_critical
from roboto.channels.model import OutboundMessage
from roboto.channels.port import Channel
from roboto.engines.port import CodingEngine
from roboto.llm.decide import Decider
from roboto.llm.port import ModelGateway, Transcriber
from roboto.orchestrator.model import RunState
from roboto.orchestrator.store import Store
from roboto.persona import anchor_line
from roboto.result import Err, Ok

# Marcadores que delimitam o CORPO LIMPO da issue na saída do refino: o motor pode narrar/pensar
# fora deles, mas o "📝 Aplicar na issue" extrai só o que está ENTRE eles (sem preâmbulo).
ISSUE_BODY_START = "===ISSUE-INICIO==="
ISSUE_BODY_END = "===ISSUE-FIM==="

# limite de tentativas do self-check de DoR no refino (1 proposta + 1 correção) — teto a tokens
_REFINE_MAX_ATTEMPTS = 2


def _marked_body(msgs: list[str]) -> str:
    """Corpo entre os marcadores da última mensagem que os tiver (vazio se não houver).

    Mesma âncora do `console._extract_proposal` (miolo `ISSUE-INICIO`/`ISSUE-FIM`, imune à quebra
    dos `===`). Usado pelo self-check de DoR: valida o que o humano veria no "📝 Aplicar".
    """
    start = ISSUE_BODY_START.strip("=")
    end = ISSUE_BODY_END.strip("=")
    for text in reversed(msgs):
        if start in text:
            inner = text.split(start, 1)[1].split(end, 1)[0]
            cleaned = inner.strip().strip("=").strip()
            if cleaned:
                return cleaned
    return ""


def _refine_prompt(
    repo: str, issue_id: str, contexto: str, correction: str = "", persona: str = ""
) -> str:
    base = (
        f"{anchor_line(persona)}"
        f"Refine a issue #{issue_id} do repo {repo}.{contexto}\n\n"
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
        "sem cercas de código). Qualquer explicação sua deve ficar FORA dos marcadores.\n\n"
        "Se o contexto trouxer uma seção `## Fontes (pesquisa web ...)`, BASEIE a decisão nessas "
        "fontes e CITE as URLs no corpo — a pesquisa já foi feita; não tente buscar de novo."
    )
    return base + correction


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
    tavily_key: str = "",
    gateway: ModelGateway | None = None,
    decider: Decider | None = None,
    code_intel: bool = False,
    persona: str = "",
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
    title = f"#{run.issue_id}"
    contexto = ""
    if run.issue_id.isdigit():
        got = await github.get_issue(run.repo, int(run.issue_id))
        if isinstance(got, Ok):
            title, corpo = got.value
            contexto = f"\n\nIssue atual — título: {title}\nCorpo atual:\n{corpo}"
            # pesquisa web HARNESS-DRIVEN (determinismo): gate em 2 degraus (keyword + Jev) decide a
            # CRITICIDADE; se crítica, o harness roda o Tavily e INJETA as fontes (modelo lê e cita,
            # não invoca tool — #203/#222).
            if tavily_key and await research_is_critical(title, corpo, decider=decider):
                block = await research_block(
                    title, corpo, tavily_key=tavily_key, gateway=gateway
                )
                if block:
                    contexto += "\n\n" + block
            # issues relacionadas (#N no corpo: "Depende de #244", "épico #67"): o harness LÊ e
            # injeta o contexto delas — consultar ≠ mexer, o refino segue read-only. Determinístico
            # (modelo local não busca sozinho — mesma lição do web/code-intel).
            self_id = int(run.issue_id) if run.issue_id.isdigit() else None
            related = await related_issues_block(
                run.repo, corpo, github.get_issue, self_id=self_id
            )
            if related:
                contexto += "\n\n" + related

    # convenções do repo-alvo (E) + recall da memória (G): mesmas injeções do impl. O refino decide
    # ESCOPO melhor conhecendo as convenções do repo e as decisões/fatos passados — harness injeta
    # (determinístico), em vez de depender do modelo "ler o AGENTS.md" ou "lembrar". Best-effort.
    conventions = read_agents_conventions(f"/work/{run.repo}")
    if conventions:
        contexto += "\n\n" + conventions
    memory = await recall_block(store, tenant, f"{title} {contexto}"[:2000])
    if memory:
        contexto += "\n\nMEMÓRIA RELEVANTE (second brain — decisões/fatos anteriores):\n" + memory

    # code-intel brief (F): injeta catálogo de tools semânticas + repo_map no prompt do refino —
    # mesmo motivo do impl (modelo subusa navegação; o harness reduz o navegar às cegas). Antes só
    # o impl recebia; o refiner navegava quase cego (medido: 0 code-intel). Best-effort (server
    # mudo → ""). Fora da thread do evento (síncrono) via to_thread.
    if code_intel:
        brief = await asyncio.to_thread(code_intel_brief, f"/work/{run.repo}")
        if brief:
            contexto += "\n\n" + brief

    # (b) DoR shift-left no refino: o motor VALIDA o próprio rascunho antes de propor e, se
    # reprovar, recebe o motivo (missing) e corrige — sem round-trip humano (determinismo primeiro).
    # O corte é o MESMO gate estrutural do `implement` (`check_issue_readiness`): a proposta não
    # chega ao humano falhando no DoR por um motivo que o código já sabe apontar.
    correction = ""
    verdict = None
    for _ in range(_REFINE_MAX_ATTEMPTS):
        prompt = _refine_prompt(run.repo, run.issue_id, contexto, correction, persona)
        res = await drive_turn(engine, store, run=run, chat_id=chat_id, now=now(), prompt=prompt)
        if isinstance(res, Err):
            return  # motor falhou: drive_turn já marcou FAILED
        if res.value is TurnOutcome.WAITING:
            return  # pausou esperando humano: deixa como está (não finaliza)
        events = await store.session_events(run.id, 0, 500)
        msgs = [e.text for e in events if e.kind == "message" and e.text.strip()]
        body = _marked_body(msgs)
        if not body:
            break  # sem marcadores: não dá p/ validar DoR — segue p/ terminal
        verdict = check_issue_readiness(IssueDraft(title=title, body=body))
        if verdict.ready:
            break
        correction = (
            "\n\nATENÇÃO: a proposta anterior REPROVOU no gate de prontidão (DoR). Faltou: "
            f"{'; '.join(verdict.missing)}. Corrija reescrevendo o CORPO COMPLETO entre os "
            "marcadores. Os itens verificáveis '- [ ]' precisam estar SOB '## Critérios de aceite' "
            "(vale dentro de subtítulos '### ...').\n\nCorpo anterior:\n" + body
        )

    # refino é TERMINAL após propor (não há PR a verificar): vai a DONE para NÃO segurar o lock
    # (tenant, issue) em 'verifying'/'running' — senão trava a implementação na mesma issue (#165).
    await store.set_state(run.id, RunState.DONE, now())
    if verdict is not None and verdict.ready:
        nota = "✅ DoR: proposta pronta para aplicar."
    elif verdict is not None:
        nota = f"⚠️ DoR ainda incompleto após correção: {'; '.join(verdict.missing)}"
    else:
        nota = "Proposta emitida (sem marcadores para validar o DoR)."
    await store.append_session_event(run.tenant, run.id, "message", now(), text=nota)


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
