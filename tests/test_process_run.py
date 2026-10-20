"""process_run_tick: pega o run da fila e dispara o motor (D22) — com StubEngine."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.loops import process_run_tick
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.orchestrator.model import GithubEvent, RunState
from roboto.orchestrator.store import InMemoryStore

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def _queue(store: InMemoryStore, key: str = "k") -> int:
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="7", agent="impl", idempotency_key=key
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    return run.id


async def test_empty_queue_is_noop() -> None:
    store = InMemoryStore()
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await process_run_tick(engine, store, tenant="acme", chat_id="5", now=lambda: _T0)
    assert engine.started == []  # nada na fila -> motor não é iniciado


async def test_claims_and_drives_to_verifying() -> None:
    store = InMemoryStore()
    run_id = await _queue(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await process_run_tick(engine, store, tenant="acme", chat_id="5", now=lambda: _T0)
    assert len(engine.started) == 1
    assert store._runs[run_id].state is RunState.VERIFYING


async def test_needs_input_pauses_run() -> None:
    store = InMemoryStore()
    run_id = await _queue(store)
    engine = StubEngine(
        [EngineEvent(EngineEventKind.NEEDS_INPUT, text="Redis ou DB?", options=["a"])]
    )
    await process_run_tick(engine, store, tenant="acme", chat_id="5", now=lambda: _T0)
    assert store._runs[run_id].state is RunState.WAITING
    effects = await store.pending_effects(10)
    assert effects[0].kind == "telegram_question"
