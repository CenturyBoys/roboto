"""Driver do turno do motor (D22) — liga `CodingEngine` ao estado (D23) e à interação humana (D24).

Inicia o motor, registra a **sessão** (mapeando o id nativo — D23), e consome os eventos:
- mensagem/tool: seguem (auditáveis);
- precisa de humano/aprovação: vira uma **interaction** via `request_human_input` (D24), a execução
  entra em `WAITING` e o turno **pausa** (retomar é um próximo `start(resume_session_id=...)` quando
  a resposta chegar);
- concluído: execução vai a `VERIFYING`; falha: `FAILED`.
Determinístico dado o motor (testável com `StubEngine`).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime
from enum import StrEnum

from roboto.app.human import request_human_input
from roboto.engines.port import CodingEngine, EngineEvent, EngineEventKind, RunSpec
from roboto.orchestrator.model import Error, InteractionKind, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result

# watchdog: segundos sem NENHUM evento do motor antes de considerar o turno TRAVADO (subprocesso
# morto/pendurado sem FINISHED/FAILED). Sem isto o run fica preso em RUNNING até o lease expirar —
# visto no PoC (o motor morria no "let's commit" e o `async for` pendurava pra sempre).
ENGINE_IDLE_TIMEOUT = float(os.environ.get("ROBOTO_ENGINE_IDLE_TIMEOUT", "300"))


async def guarded_events(
    events: AsyncIterator[EngineEvent], idle_timeout: float | None = None
) -> AsyncIterator[EngineEvent]:
    """Repassa os eventos do motor com watchdog de INATIVIDADE: se passar `idle_timeout`s sem
    nenhum evento, levanta `TimeoutError` em vez de pendurar o turno. O chamador trata como FAILED,
    então o run sai de RUNNING (destrava o lock por issue e permite retry). `idle_timeout=None` lê
    `ENGINE_IDLE_TIMEOUT` em call-time (monkeypatchável em teste)."""
    timeout = ENGINE_IDLE_TIMEOUT if idle_timeout is None else idle_timeout
    it = events.__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(it.__anext__(), timeout)
        except StopAsyncIteration:
            return
        yield event


class TurnOutcome(StrEnum):
    WAITING = "waiting"  # pausou esperando humano
    FINISHED = "finished"  # concluiu (-> verifying)
    COMPLETED = "completed"  # stream terminou sem finished explícito
    FAILED = "failed"


async def drive_turn(
    engine: CodingEngine,
    store: Store,
    *,
    run: Run,
    chat_id: str,
    now: datetime,
    prompt: str | None = None,
) -> Result[TurnOutcome, Error]:
    spec = RunSpec(
        tenant=run.tenant,
        repo=run.repo,
        workdir=f"/work/{run.repo}",
        prompt=prompt or f"Trabalhe a issue {run.issue_id} do repo {run.repo}.",
        resume_session_id=None,
    )
    started = await engine.start(spec)
    if isinstance(started, Err):
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(started.error)

    session = await store.create_session(run.tenant, run.id, engine.engine, now)
    await store.set_native_session(session.id, started.value, now)
    await store.set_state(run.id, RunState.RUNNING, now)

    try:
        async for event in guarded_events(engine.events()):
            if event.kind is EngineEventKind.MESSAGE and event.text:  # feed ao vivo (Fatia 2)
                await store.append_session_event(
                    run.tenant, run.id, "message", now, text=event.text, session_id=session.id
                )
            elif event.kind is EngineEventKind.TOOL_CALL:
                await store.append_session_event(
                    run.tenant, run.id, "tool_call", now, tool=event.tool, session_id=session.id
                )
            if event.kind in (EngineEventKind.NEEDS_INPUT, EngineEventKind.NEEDS_APPROVAL):
                kind = _interaction_kind(event.kind, event.options)
                prompt = _prompt_for(event)
                await request_human_input(
                    store,
                    tenant=run.tenant,
                    execution_id=run.id,
                    chat_id=chat_id,
                    kind=kind,
                    prompt=prompt,
                    options=event.options,
                    now=now,
                    session_id=session.id,
                )
                return Ok(TurnOutcome.WAITING)
            if event.kind is EngineEventKind.FINISHED:
                await store.set_state(run.id, RunState.VERIFYING, now)
                return Ok(TurnOutcome.FINISHED)
            if event.kind is EngineEventKind.FAILED:
                await store.set_state(run.id, RunState.FAILED, now)
                return Err(Error("engine", event.text or "falha no motor"))
    except TimeoutError:
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(Error("engine", "motor travado: watchdog de inatividade (subprocesso morto?)"))
    return Ok(TurnOutcome.COMPLETED)


def _interaction_kind(event_kind: EngineEventKind, options: list[str]) -> InteractionKind:
    if event_kind is EngineEventKind.NEEDS_APPROVAL:
        return InteractionKind.APPROVAL
    return InteractionKind.DECISION if options else InteractionKind.QUESTION


def _prompt_for(event: EngineEvent) -> str:
    if event.kind is EngineEventKind.NEEDS_APPROVAL:
        action = f" ({event.tool})" if event.tool else ""
        return f"Aprovar ação{action}? {event.text}".strip()
    return event.text
