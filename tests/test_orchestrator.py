"""Testes tier-1 do orquestrador (determinísticos, store em memória, sem LLM)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from roboto.orchestrator import (
    GithubEvent,
    InMemoryStore,
    RunState,
    StubPublisher,
    StubRunner,
    enqueue_effect,
    ingest,
    process_next,
    publish_outbox,
    sweep,
)

T0 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)


def _ev(key: str = "k1") -> GithubEvent:
    return GithubEvent(
        tenant="acme", repo="acme/app", issue_id="42", agent="refino", idempotency_key=key
    )


async def test_ingest_is_idempotent() -> None:
    store = InMemoryStore()
    first = await ingest(store, _ev(), T0)
    second = await ingest(store, _ev(), T0)
    assert first.is_ok and second.is_ok
    assert first.unwrap().id == second.unwrap().id  # mesma run, não duplica
    assert first.unwrap().state == RunState.QUEUED


async def test_process_dispatches_once() -> None:
    store, runner = InMemoryStore(), StubRunner()
    await ingest(store, _ev(), T0)
    first = await process_next(store, runner, "acme", T0)
    assert first.is_ok and first.unwrap() is not None
    assert len(runner.dispatched) == 1
    second = await process_next(store, runner, "acme", T0)
    assert second.is_ok and second.unwrap() is None  # fila vazia -> sem 2º dispatch
    assert len(runner.dispatched) == 1


async def test_state_is_running_before_effect() -> None:
    store, runner = InMemoryStore(), StubRunner()
    await ingest(store, _ev(), T0)
    await process_next(store, runner, "acme", T0)
    assert runner.dispatched[0].state == RunState.RUNNING


async def test_outbox_dedup_and_publish() -> None:
    store, pub = InMemoryStore(), StubPublisher()
    run = (await ingest(store, _ev(), T0)).unwrap()
    created = await enqueue_effect(store, run, "telegram_notify", {"m": "oi"}, "d1", T0)
    dup = await enqueue_effect(store, run, "telegram_notify", {"m": "oi"}, "d1", T0)
    assert created.unwrap() is True and dup.unwrap() is False  # dedup por dedup_key
    first = await publish_outbox(store, pub, T0)
    assert first.unwrap() == 1 and len(pub.sent) == 1
    again = await publish_outbox(store, pub, T0)
    assert again.unwrap() == 0  # nada pendente após enviar


async def test_sweep_requeue_then_fail() -> None:
    store, runner = InMemoryStore(), StubRunner()
    await ingest(store, _ev(), T0)
    await process_next(store, runner, "acme", T0, lease_seconds=60)
    later = T0 + timedelta(seconds=120)
    first = await sweep(store, later, max_attempts=2)
    assert first.unwrap() == 1  # lease expirada -> re-enfileira (attempt 1)
    await process_next(store, runner, "acme", later, lease_seconds=60)
    later2 = later + timedelta(seconds=120)
    second = await sweep(store, later2, max_attempts=2)
    assert second.unwrap() == 1  # attempt 2 >= teto -> FAILED
    final = await process_next(store, runner, "acme", later2)
    assert final.unwrap() is None  # falhado, não volta à fila


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            asyncio.run(_fn())
            print(f"ok  {_name}")
    print("todos os testes do orquestrador passaram")
