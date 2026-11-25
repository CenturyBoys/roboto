"""Watchdog de inatividade (engine_loop) — pausa enquanto há aprovação humana PENDENTE."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from roboto.app.engine_loop import guarded_events, has_pending_approval
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.orchestrator.model import InteractionKind
from roboto.orchestrator.store import InMemoryStore

_T0 = datetime(2026, 11, 24, tzinfo=UTC)


async def _one_then_stall() -> object:
    """Emite 1 evento e depois fica MUDO (motor bloqueado esperando humano)."""
    yield EngineEvent(EngineEventKind.MESSAGE, text="começando")
    await asyncio.Event().wait()  # trava pra sempre


async def test_watchdog_estoura_sem_humano() -> None:
    # sem aprovação pendente, o silêncio = stall → TimeoutError (comportamento original).
    got: list[str] = []
    with pytest.raises(TimeoutError):
        async for e in guarded_events(_one_then_stall(), idle_timeout=0.02):
            got.append(e.text or "")
    assert got == ["começando"]


async def test_watchdog_pausa_enquanto_aprovacao_pendente() -> None:
    # REGRESSÃO (run-1050): motor bloqueado num gate humano NÃO pode ser morto pelo watchdog. O
    # awaiting_human segura 2 janelas (humano pensando) e na 3ª já respondeu → aí sim estoura.
    checagens = {"n": 0}

    async def awaiting() -> bool:
        checagens["n"] += 1
        return checagens["n"] <= 2  # pendente 2x; depois resolvido

    got: list[str] = []
    with pytest.raises(TimeoutError):
        async for e in guarded_events(
            _one_then_stall(), idle_timeout=0.02, awaiting_human=awaiting
        ):
            got.append(e.text or "")
    assert got == ["começando"]
    assert checagens["n"] == 3  # re-esperou 2x; na 3ª sem pendente → estourou


async def test_has_pending_approval_reflete_o_store() -> None:
    store = InMemoryStore()
    assert await has_pending_approval(store, 1050) is False
    it = await store.create_interaction(
        "acme", 1050, InteractionKind.APPROVAL, "Write migration.sql", ["allow", "deny"], _T0
    )
    assert await has_pending_approval(store, 1050) is True  # aprovação pendente
    await store.answer_interaction(it.id, "allow", "console", _T0)
    assert await has_pending_approval(store, 1050) is False  # respondida → não bloqueia mais
