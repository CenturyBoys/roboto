"""Smoke da Fase 0 (N3): prova o encanamento SEM secrets e SEM tocar o GitHub.

Aplica as migrações, enfileira um run e roda o laço claim->motor com o `StubEngine`; confere que o
run avançou para VERIFYING. Só precisa de `DATABASE_URL`. Sai 0 (ok) / 1 (falhou).
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from roboto.app.loops import process_run_tick
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.orchestrator.model import GithubEvent, RunState
from roboto.orchestrator.pg_store import PostgresStore

_TABLES = "run, run_event, outbox, llm_call, session, interaction"
_MIGRATIONS = sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql"))


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[smoke] DATABASE_URL não definido")
        return 1

    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        for migration in _MIGRATIONS:
            await conn.execute(migration.read_text())
        await conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    store = PostgresStore(pool)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    event = GithubEvent(
        tenant="poc", repo="arenavalendo/main", issue_id="1", agent="impl", idempotency_key="poc-1"
    )
    run, _ = await store.insert_run_if_absent(event, now)
    engine = StubEngine(
        [EngineEvent(EngineEventKind.MESSAGE, text="oi"), EngineEvent(EngineEventKind.FINISHED)]
    )
    await process_run_tick(engine, store, tenant="poc", chat_id="0", now=lambda: now)
    got = await store.get_run(run.id)
    await store.close()

    ok = got is not None and got.state is RunState.VERIFYING and len(engine.started) == 1
    state = got.state if got is not None else None
    print(
        f"[smoke] run {run.id}: state={state} engine.started={len(engine.started)} "
        f"-> {'OK' if ok else 'FALHOU'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
