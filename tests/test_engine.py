"""Motor de coding (D22): driver liga eventos do motor ao estado (D23) e à interação (D24)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import roboto.app.engine_loop as engine_loop
from roboto.app.engine_loop import TurnOutcome, drive_turn
from roboto.engines.capabilities import CAPABILITIES, Capability
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.orchestrator.model import (
    Engine,
    GithubEvent,
    InteractionKind,
    RunState,
)
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def _run(store: InMemoryStore):  # type: ignore[no-untyped-def]
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="7", agent="impl", idempotency_key="k"
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    return run


async def test_needs_input_pauses_and_creates_interaction() -> None:
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine(
        [
            EngineEvent(EngineEventKind.MESSAGE, text="analisando..."),
            EngineEvent(EngineEventKind.NEEDS_INPUT, text="Redis ou DB?", options=["Redis", "DB"]),
            EngineEvent(EngineEventKind.FINISHED),  # não deve ser alcançado (pausa antes)
        ]
    )
    outcome = await drive_turn(engine, store, run=run, chat_id="5", now=_T0)
    assert isinstance(outcome, Ok)
    assert outcome.value is TurnOutcome.WAITING
    assert store._runs[run.id].state is RunState.WAITING  # AWAITING_HUMAN
    # sessão registrada com id nativo mapeado (D23)
    session = next(iter(store._sessions.values()))
    assert session.native_session_id == "stub-session"
    # pergunta enfileirada no outbox com a decisão e opções (D24)
    effects = await store.pending_effects(10)
    assert len(effects) == 1
    assert effects[0].kind == "telegram_question"
    assert "Redis ou DB?" in effects[0].payload["text"]
    interaction = next(iter(store._interactions.values()))
    assert interaction.kind is InteractionKind.DECISION


async def test_needs_approval_is_approval_kind() -> None:
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine(
        [EngineEvent(EngineEventKind.NEEDS_APPROVAL, text="rm -rf build", tool="Bash")]
    )
    outcome = await drive_turn(engine, store, run=run, chat_id="5", now=_T0)
    assert isinstance(outcome, Ok)
    assert outcome.value is TurnOutcome.WAITING
    interaction = next(iter(store._interactions.values()))
    assert interaction.kind is InteractionKind.APPROVAL
    assert "Aprovar" in interaction.prompt


async def test_finished_goes_to_verifying() -> None:
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine(
        [EngineEvent(EngineEventKind.MESSAGE, text="pronto"), EngineEvent(EngineEventKind.FINISHED)]
    )
    outcome = await drive_turn(engine, store, run=run, chat_id="5", now=_T0)
    assert isinstance(outcome, Ok)
    assert outcome.value is TurnOutcome.FINISHED
    assert store._runs[run.id].state is RunState.VERIFYING
    assert await store.pending_effects(10) == []


async def test_failed_sets_run_failed() -> None:
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FAILED, text="boom")])
    outcome = await drive_turn(engine, store, run=run, chat_id="5", now=_T0)
    assert isinstance(outcome, Err)
    assert outcome.error.kind == "engine"
    assert store._runs[run.id].state is RunState.FAILED


class _StallEngine(StubEngine):
    """Motor que NUNCA emite evento dentro do watchdog (simula subprocesso morto sem FINISHED)."""

    async def events(self):  # type: ignore[no-untyped-def]
        await asyncio.sleep(3600)
        if False:  # pragma: no cover — mantém isto um async generator sem emitir nada
            yield EngineEvent(EngineEventKind.FINISHED)


async def test_engine_stall_fails_instead_of_hanging(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # watchdog: motor pendurado (sem FINISHED/FAILED) -> FAILED, não trava o run em RUNNING.
    monkeypatch.setattr(engine_loop, "ENGINE_IDLE_TIMEOUT", 0.01)
    store = InMemoryStore()
    run = await _run(store)
    outcome = await drive_turn(_StallEngine([]), store, run=run, chat_id="5", now=_T0)
    assert isinstance(outcome, Err)
    assert outcome.error.kind == "engine"
    assert store._runs[run.id].state is RunState.FAILED


async def test_capability_matrix_covers_both_engines() -> None:
    assert set(CAPABILITIES) == {Engine.CLAUDE_CODE, Engine.CODEX}
    for engine, caps in CAPABILITIES.items():
        assert set(caps) == set(Capability), f"{engine} faltando capacidades"
        # o ponto sensível (aprovação por ação no Codex) é 'partial' — exige PoC
    assert CAPABILITIES[Engine.CODEX][Capability.APPROVE_PER_ACTION].level == "partial"
