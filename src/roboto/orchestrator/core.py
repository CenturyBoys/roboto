"""Núcleo determinístico do orquestrador (ver docs/design/orquestrador.md).

Não chama LLM. Tudo retorna ``Result`` (D1). Invariantes: estado antes do efeito; reconferir no
lock (no store); gravar->commit->efetuar (outbox); tenant em tudo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
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


_BACKOFF_BASE_S = 30
_BACKOFF_FACTOR = 2
_BACKOFF_CAP_S = 3600


def backoff_until(attempt: int, now: datetime) -> datetime:
    """Próxima tentativa com backoff exponencial: 30s, 60s, 120s... (teto 1h). ``attempt`` >= 1."""
    delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (_BACKOFF_FACTOR ** max(0, attempt - 1)))
    return now + timedelta(seconds=delay)


async def publish_outbox(
    store: Store, publisher: Publisher, now: datetime, limit: int = 100, max_attempts: int = 5
) -> Result[int, Error]:
    """Efetua os efeitos pendentes (gravar->commit->efetuar) e marca como enviados.

    Processa item a item: a falha de UM efeito não interrompe o lote. Em falha, o item é **adiado**
    com backoff exponencial (não bloqueia os demais); ao esgotar ``max_attempts`` vai para a
    **dead-letter** (com contexto do erro, p/ replay manual). Retorna quantos foram enviados.
    """
    sent = 0
    for item in await store.pending_effects(limit):
        if item.next_attempt_at is not None and item.next_attempt_at > now:
            continue  # ainda em backoff — não tenta antes da hora
        outcome = await publisher.send(item)
        if isinstance(outcome, Err):
            attempt = item.attempt + 1
            if attempt >= max_attempts:
                await store.dead_letter_effect(item.id, str(outcome.error), now)
            else:
                await store.defer_effect(item.id, attempt, backoff_until(attempt, now), now)
            continue
        await store.mark_sent(item.id, now)
        sent += 1
    return Ok(sent)


async def sweep(store: Store, now: datetime, max_attempts: int = 3) -> Result[int, Error]:
    """Reclama runs abandonados (lease expirada): re-enfileira com backoff ou manda à dead-letter.

    Antes de reclamável de novo, o run espera o backoff (``next_attempt_at``). Ao estourar
    ``max_attempts`` vai para a dead-letter (com contexto), em vez de só virar FAILED mudo.
    """
    abandoned = await store.find_abandoned(now)
    for run in abandoned:
        next_attempt = run.attempt + 1
        if next_attempt < max_attempts:
            await store.requeue_run_with_backoff(
                run.id, next_attempt, backoff_until(next_attempt, now), now
            )
        else:
            await store.dead_letter_run(
                run.id, f"lease esgotado após {next_attempt} tentativa(s)", now
            )
    return Ok(len(abandoned))
