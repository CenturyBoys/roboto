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
from roboto.orchestrator.model import Error, OutboxItem
from roboto.result import Err, Ok, Result

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


class _FailOnePublisher:
    """Publisher que falha só no kind 'ruim' e registra os demais (simula efeito venenoso)."""

    def __init__(self) -> None:
        self.sent: list[OutboxItem] = []

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        if item.kind == "ruim":
            return Err(Error("effect", "falha proposital"))
        self.sent.append(item)
        return Ok(None)


async def test_outbox_efeito_venenoso_nao_bloqueia_o_lote() -> None:
    store, pub = InMemoryStore(), _FailOnePublisher()
    run = (await ingest(store, _ev(), T0)).unwrap()
    await enqueue_effect(store, run, "ruim", {"m": "x"}, "d-ruim", T0)  # venenoso, enfileirado 1º
    await enqueue_effect(store, run, "telegram_notify", {"m": "ok"}, "d-ok", T0)
    sent = await publish_outbox(store, pub, T0)
    assert sent.unwrap() == 1 and len(pub.sent) == 1  # o bom foi enviado APESAR do venenoso
    assert pub.sent[0].kind == "telegram_notify"
    again = await publish_outbox(store, pub, T0)
    assert again.unwrap() == 0  # venenoso segue pendente p/ retry, sem bloquear a drenagem


async def test_sweep_requeue_backoff_then_dead_letter() -> None:
    store, runner = InMemoryStore(), StubRunner()
    await ingest(store, _ev(), T0)
    await process_next(store, runner, "acme", T0, lease_seconds=60)
    later = T0 + timedelta(seconds=120)
    first = await sweep(store, later, max_attempts=2)
    assert first.unwrap() == 1  # lease expirada -> re-enfileira (attempt 1) com backoff
    # backoff: ainda NÃO reclamável imediatamente (next_attempt_at no futuro)
    assert await store.claim_next_queued("acme", later, 60) is None
    # após a janela de backoff, reclamável de novo
    claim_at = later + timedelta(seconds=90)
    await process_next(store, runner, "acme", claim_at, lease_seconds=60)
    later2 = claim_at + timedelta(seconds=120)
    second = await sweep(store, later2, max_attempts=2)
    assert second.unwrap() == 1  # attempt 2 >= teto -> dead-letter (não só FAILED mudo)
    final = await process_next(store, runner, "acme", later2 + timedelta(seconds=120))
    assert final.unwrap() is None  # em dead-letter, não volta à fila
    dl = await store.list_dead_letter("acme")
    assert len(dl) == 1 and dl[0].source == "run"


async def test_outbox_backoff_dead_letter_and_replay() -> None:
    store, pub = InMemoryStore(), _FailOnePublisher()
    run = (await ingest(store, _ev(), T0)).unwrap()
    await enqueue_effect(store, run, "ruim", {"m": "x"}, "d1", T0)
    # max_attempts=2: 1ª falha -> adia (backoff); 2ª falha -> dead-letter
    moment = T0
    for _ in range(4):
        await publish_outbox(store, pub, moment, max_attempts=2)
        moment = moment + timedelta(hours=2)  # avança além do backoff
    dead = await store.list_dead_letter("acme")
    assert len(dead) == 1 and dead[0].source == "effect" and dead[0].kind == "ruim"
    # replay volta o efeito à fila; publisher que aceita agora -> envia
    good = StubPublisher()
    assert await store.replay_dead_letter(dead[0].id, moment) is True
    sent = await publish_outbox(store, good, moment)
    assert sent.unwrap() == 1 and len(good.sent) == 1
    assert await store.list_dead_letter("acme") == []


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            asyncio.run(_fn())
            print(f"ok  {_name}")
    print("todos os testes do orquestrador passaram")
