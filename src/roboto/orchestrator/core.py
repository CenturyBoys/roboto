"""Núcleo determinístico do orquestrador (ver docs/design/orquestrador.md).

Não chama LLM. Tudo retorna ``Result`` (D1). Invariantes: estado antes do efeito; reconferir no
lock (no store); gravar->commit->efetuar (outbox); tenant em tudo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from roboto.orchestrator.model import Error, GithubEvent, Run, RunState
from roboto.orchestrator.runner import Publisher, Runner
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result


async def ingest(store: Store, ev: GithubEvent, now: datetime) -> Result[Run, Error]:
    """Persiste o run de forma idempotente (estado=queued). Duplicado retorna o mesmo run."""
    run, _created = await store.insert_run_if_absent(ev, now)
    return Ok(run)


async def process_next(
    store: Store, runner: Runner, tenant: str, now: datetime, lease_seconds: int = 300
) -> Result[Run | None, Error]:
    """Pega o próximo run (lock+reconferir -> RUNNING antes do efeito) e dispara o runner."""
    run = await store.claim_next_queued(tenant, now, lease_seconds)
    if run is None:
        return Ok[Run | None](None)
    outcome = await runner.dispatch(run)
    if isinstance(outcome, Err):
        await store.set_state(run.id, RunState.FAILED, now)
        return Err(outcome.error)
    return Ok[Run | None](run)


async def enqueue_effect(
    store: Store, run: Run, kind: str, payload: dict[str, Any], dedup_key: str, now: datetime
) -> Result[bool, Error]:
    """Enfileira um efeito no outbox (idempotente por dedup_key). Grava na MESMA tx do estado."""
    created = await store.enqueue_effect(run.tenant, run.id, kind, payload, dedup_key, now)
    return Ok(created)


async def publish_outbox(
    store: Store, publisher: Publisher, now: datetime, limit: int = 100
) -> Result[int, Error]:
    """Efetua os efeitos pendentes (gravar->commit->efetuar) e marca como enviados."""
    sent = 0
    for item in await store.pending_effects(limit):
        outcome = await publisher.send(item)
        if isinstance(outcome, Err):
            return Err(outcome.error)
        await store.mark_sent(item.id, now)
        sent += 1
    return Ok(sent)


async def sweep(store: Store, now: datetime, max_attempts: int = 3) -> Result[int, Error]:
    """Reclama runs abandonados (lease expirada): re-enfileira ou falha ao estourar o teto."""
    abandoned = await store.find_abandoned(now)
    for run in abandoned:
        next_attempt = run.attempt + 1
        target = RunState.QUEUED if next_attempt < max_attempts else RunState.FAILED
        await store.set_state(run.id, target, now, attempt=next_attempt)
    return Ok(len(abandoned))
