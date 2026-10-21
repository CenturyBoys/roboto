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

from roboto.orchestrator.model import (
    Engine,
    GithubEvent,
    Interaction,
    InteractionKind,
    InteractionStatus,
    LlmCall,
    MemoryFact,
    OutboxItem,
    Run,
    RunState,
    Session,
)

_RUN_COLS = (
    "id, tenant, repo, issue_id, agent, state, attempt, "
    "idempotency_key, created_at, updated_at, lease_until, origin_chat_id"
)
_OUTBOX_COLS = "id, tenant, run_id, kind, payload, dedup_key, status, created_at, sent_at"
_SESSION_COLS = (
    "id, tenant, execution_id, engine, native_session_id, state, created_at, updated_at"
)
_INTERACTION_COLS = (
    "id, tenant, execution_id, session_id, kind, prompt, options, status, "
    "channel_message_id, answer, answered_by, created_at, expires_at, answered_at"
)


def _row_to_fact(row: Any) -> MemoryFact:
    return MemoryFact(
        id=row["id"], tenant=row["tenant"], kind=row["kind"], ref=row["ref"],
        text=row["text"], created_at=row["created_at"],
    )


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
        origin_chat_id=row["origin_chat_id"],
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


def _row_to_session(row: Any) -> Session:
    return Session(
        id=row["id"],
        tenant=row["tenant"],
        execution_id=row["execution_id"],
        engine=Engine(row["engine"]),
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        native_session_id=row["native_session_id"],
    )


def _row_to_interaction(row: Any) -> Interaction:
    options = row["options"]
    if isinstance(options, str):
        options = json.loads(options)
    return Interaction(
        id=row["id"],
        tenant=row["tenant"],
        execution_id=row["execution_id"],
        kind=InteractionKind(row["kind"]),
        prompt=row["prompt"],
        options=list(options),
        status=InteractionStatus(row["status"]),
        created_at=row["created_at"],
        session_id=row["session_id"],
        channel_message_id=row["channel_message_id"],
        answer=row["answer"],
        answered_by=row["answered_by"],
        expires_at=row["expires_at"],
        answered_at=row["answered_at"],
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
                                 idempotency_key, created_at, updated_at, origin_chat_id)
                VALUES ($1, $2, $3, $4, $5, 0, $6, $7, $7, $8)
                ON CONFLICT (tenant, idempotency_key) DO NOTHING
                RETURNING {_RUN_COLS}
                """,
                ev.tenant, ev.repo, ev.issue_id, ev.agent, RunState.QUEUED.value,
                ev.idempotency_key, now, ev.origin_chat_id,
            )
            if row is not None:
                return _row_to_run(row), True
            existing = await conn.fetchrow(
                f"SELECT {_RUN_COLS} FROM run WHERE tenant = $1 AND idempotency_key = $2",
                ev.tenant, ev.idempotency_key,
            )
            return _row_to_run(existing), False

    async def claim_next_queued(
        self, tenant: str, now: datetime, lease_seconds: int, *, agent: str | None = None
    ) -> Run | None:
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self._pool.acquire() as conn, conn.transaction():
            picked = await conn.fetchrow(
                """
                SELECT id FROM run
                WHERE tenant = $1 AND state = 'queued' AND ($2::text IS NULL OR agent = $2)
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                tenant, agent,
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

    async def create_session(
        self, tenant: str, execution_id: int, engine: Engine, now: datetime
    ) -> Session:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO session (tenant, execution_id, engine, state, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', $4, $4)
                RETURNING {_SESSION_COLS}
                """,
                tenant, execution_id, engine.value, now,
            )
            return _row_to_session(row)

    async def set_native_session(
        self, session_id: int, native_session_id: str, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE session SET native_session_id = $2, updated_at = $3 WHERE id = $1",
                session_id, native_session_id, now,
            )

    async def create_interaction(
        self,
        tenant: str,
        execution_id: int,
        kind: InteractionKind,
        prompt: str,
        options: list[str],
        now: datetime,
        session_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> Interaction:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO interaction
                    (tenant, execution_id, session_id, kind, prompt, options, status,
                     created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'pending', $7, $8)
                RETURNING {_INTERACTION_COLS}
                """,
                tenant, execution_id, session_id, kind.value, prompt,
                json.dumps(options), now, expires_at,
            )
            return _row_to_interaction(row)

    async def set_interaction_message_id(
        self, interaction_id: int, channel_message_id: str
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE interaction SET channel_message_id = $2 WHERE id = $1",
                interaction_id, channel_message_id,
            )

    async def get_interaction_by_message_id(
        self, tenant: str, channel_message_id: str
    ) -> Interaction | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_INTERACTION_COLS} FROM interaction "
                "WHERE tenant = $1 AND channel_message_id = $2",
                tenant, channel_message_id,
            )
            return _row_to_interaction(row) if row is not None else None

    async def answer_interaction(
        self, interaction_id: int, answer: str, answered_by: str, now: datetime
    ) -> bool:
        async with self._pool.acquire() as conn:
            # 1ª resposta válida vence: só atualiza se ainda 'pending' (atômico no DB)
            row = await conn.fetchrow(
                """
                UPDATE interaction
                SET status = 'answered', answer = $2, answered_by = $3, answered_at = $4
                WHERE id = $1 AND status = 'pending'
                RETURNING id
                """,
                interaction_id, answer, answered_by, now,
            )
            return row is not None

    async def pending_interactions(self, tenant: str, limit: int) -> list[Interaction]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_INTERACTION_COLS} FROM interaction "
                "WHERE tenant = $1 AND status = 'pending' ORDER BY id LIMIT $2",
                tenant, limit,
            )
            return [_row_to_interaction(r) for r in rows]

    async def list_runs(self, tenant: str, limit: int) -> list[Run]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_RUN_COLS} FROM run WHERE tenant = $1 ORDER BY id DESC LIMIT $2",
                tenant, limit,
            )
            return [_row_to_run(r) for r in rows]

    async def get_run(self, run_id: int) -> Run | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {_RUN_COLS} FROM run WHERE id = $1", run_id)
            return _row_to_run(row) if row is not None else None

    async def sessions_for_execution(self, execution_id: int) -> list[Session]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SESSION_COLS} FROM session WHERE execution_id = $1 ORDER BY id",
                execution_id,
            )
            return [_row_to_session(r) for r in rows]

    async def interactions_for_execution(self, execution_id: int) -> list[Interaction]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_INTERACTION_COLS} FROM interaction WHERE execution_id = $1 ORDER BY id",
                execution_id,
            )
            return [_row_to_interaction(r) for r in rows]

    async def record_llm_call(
        self,
        *,
        tenant: str,
        run_id: int | None,
        provider: str,
        model: str,
        tier: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        now: datetime,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO llm_call
                    (tenant, run_id, provider, model, tier, tokens_in, tokens_out, cost_usd, at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                tenant, run_id, provider, model, tier, tokens_in, tokens_out, cost_usd, now,
            )

    async def llm_calls(self, tenant: str, limit: int) -> list[LlmCall]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, tenant, run_id, model, tier, tokens_in, tokens_out, cost_usd, at "
                "FROM llm_call WHERE tenant = $1 ORDER BY id LIMIT $2",
                tenant, limit,
            )
            return [
                LlmCall(
                    id=r["id"],
                    tenant=r["tenant"],
                    run_id=r["run_id"],
                    model=r["model"],
                    tier=r["tier"],
                    tokens_in=r["tokens_in"],
                    tokens_out=r["tokens_out"],
                    cost_usd=float(r["cost_usd"]),
                    at=r["at"],
                )
                for r in rows
            ]

    async def remember(
        self, tenant: str, text: str, *, kind: str, ref: str, now: datetime
    ) -> MemoryFact:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO memory_fact (tenant, kind, ref, text, created_at) "
                "VALUES ($1,$2,$3,$4,$5) RETURNING id,tenant,kind,ref,text,created_at",
                tenant, kind, ref, text, now,
            )
            return _row_to_fact(row)

    async def recall(self, tenant: str, query: str, limit: int) -> list[MemoryFact]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id,tenant,kind,ref,text,created_at FROM memory_fact "
                "WHERE tenant = $1 AND fts @@ websearch_to_tsquery('portuguese', $2) "
                "ORDER BY ts_rank(fts, websearch_to_tsquery('portuguese', $2)) DESC LIMIT $3",
                tenant, query, limit,
            )
            return [_row_to_fact(r) for r in rows]

    async def get_channel_offset(self, tenant: str, channel: str) -> int | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT cursor_val FROM channel_cursor WHERE tenant = $1 AND channel = $2",
                tenant, channel,
            )
            return int(row["cursor_val"]) if row is not None else None

    async def set_channel_offset(
        self, tenant: str, channel: str, offset: int, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channel_cursor (tenant, channel, cursor_val, updated_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tenant, channel) DO UPDATE
                    SET cursor_val = $3, updated_at = $4
                """,
                tenant, channel, offset, now,
            )
