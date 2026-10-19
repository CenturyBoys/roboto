"""Implementação Postgres da porta ``Store`` (asyncpg).

Mesma interface do ``InMemoryStore`` (determinismo primeiro: a troca é por interface). Aqui o
lock/serialização é **real** — ``claim_next_queued`` usa ``FOR UPDATE SKIP LOCKED`` (reconferir
dentro do lock, sem corrida entre workers). Schema = ``migrations/0001_init.sql``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from roboto.orchestrator.model import GithubEvent, OutboxItem, Run, RunState

_RUN_COLS = (
    "id, tenant, repo, issue_id, agent, state, attempt, "
    "idempotency_key, created_at, updated_at, lease_until"
)
_OUTBOX_COLS = "id, tenant, run_id, kind, payload, dedup_key, status, created_at, sent_at"


def _row_to_run(row: Any) -> Run:
    return Run(
        id=row["id"],
        tenant=row["tenant"],
        repo=row["repo"],
        issue_id=row["issue_id"],
        agent=row["agent"],
        state=RunState(row["state"]),
        attempt=row["attempt"],
        idempotency_key=row["idempotency_key"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        lease_until=row["lease_until"],
    )


def _row_to_outbox(row: Any) -> OutboxItem:
    payload = row["payload"]
    if isinstance(payload, str):  # asyncpg devolve jsonb como str por padrão
        payload = json.loads(payload)
    return OutboxItem(
        id=row["id"],
        tenant=row["tenant"],
        run_id=row["run_id"],
        kind=row["kind"],
        payload=payload,
        dedup_key=row["dedup_key"],
        status=row["status"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
    )


class PostgresStore:
    """Store sobre Postgres. Construa via ``await PostgresStore.connect(dsn)``."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresStore:
        pool = await asyncpg.create_pool(dsn)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def insert_run_if_absent(self, ev: GithubEvent, now: datetime) -> tuple[Run, bool]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO run (tenant, repo, issue_id, agent, state, attempt,
                                 idempotency_key, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 0, $6, $7, $7)
                ON CONFLICT (tenant, idempotency_key) DO NOTHING
                RETURNING {_RUN_COLS}
                """,
                ev.tenant, ev.repo, ev.issue_id, ev.agent, RunState.QUEUED.value,
                ev.idempotency_key, now,
            )
            if row is not None:
                return _row_to_run(row), True
            existing = await conn.fetchrow(
                f"SELECT {_RUN_COLS} FROM run WHERE tenant = $1 AND idempotency_key = $2",
                ev.tenant, ev.idempotency_key,
            )
            return _row_to_run(existing), False

    async def claim_next_queued(
        self, tenant: str, now: datetime, lease_seconds: int
    ) -> Run | None:
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self._pool.acquire() as conn, conn.transaction():
            picked = await conn.fetchrow(
                """
                SELECT id FROM run
                WHERE tenant = $1 AND state = 'queued'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                tenant,
            )
            if picked is None:
                return None
            row = await conn.fetchrow(
                f"""
                UPDATE run SET state = 'running', lease_until = $2, updated_at = $2
                WHERE id = $1
                RETURNING {_RUN_COLS}
                """,
                picked["id"], lease_until,
            )
            return _row_to_run(row)

    async def set_state(
        self, run_id: int, state: RunState, now: datetime, attempt: int | None = None
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE run SET
                    state = $2,
                    updated_at = $3,
                    attempt = COALESCE($4, attempt),
                    lease_until = CASE WHEN $2 = 'running' THEN lease_until ELSE NULL END
                WHERE id = $1
                """,
                run_id, state.value, now, attempt,
            )

    async def enqueue_effect(
        self,
        tenant: str,
        run_id: int,
        kind: str,
        payload: dict[str, Any],
        dedup_key: str,
        now: datetime,
    ) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO outbox (tenant, run_id, kind, payload, dedup_key, status, created_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, 'pending', $6)
                ON CONFLICT (tenant, dedup_key) DO NOTHING
                RETURNING id
                """,
                tenant, run_id, kind, json.dumps(payload), dedup_key, now,
            )
            return row is not None

    async def pending_effects(self, limit: int) -> list[OutboxItem]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_OUTBOX_COLS} FROM outbox WHERE status = 'pending' ORDER BY id LIMIT $1",
                limit,
            )
            return [_row_to_outbox(r) for r in rows]

    async def mark_sent(self, effect_id: int, now: datetime) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE outbox SET status = 'sent', sent_at = $2 WHERE id = $1",
                effect_id, now,
            )

    async def find_abandoned(self, now: datetime) -> list[Run]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_RUN_COLS} FROM run
                WHERE state = 'running' AND lease_until IS NOT NULL AND lease_until < $1
                ORDER BY id
                """,
                now,
            )
            return [_row_to_run(r) for r in rows]
