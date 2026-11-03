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
    DeadLetter,
    Engine,
    ExecutionPr,
    GithubEvent,
    Interaction,
    InteractionKind,
    InteractionStatus,
    LlmCall,
    MemoryFact,
    OutboxItem,
    PrState,
    Run,
    RunState,
    Session,
    SessionEvent,
)

_RUN_COLS = (
    "id, tenant, repo, issue_id, agent, state, attempt, "
    "idempotency_key, created_at, updated_at, lease_until, origin_chat_id, next_attempt_at"
)
_OUTBOX_COLS = (
    "id, tenant, run_id, kind, payload, dedup_key, status, created_at, sent_at, "
    "attempt, next_attempt_at"
)
_DEAD_LETTER_COLS = (
    "id, tenant, source, ref_id, kind, payload, error, attempts, created_at"
)
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


def _row_to_session_event(row: Any) -> SessionEvent:
    return SessionEvent(
        id=row["id"], tenant=row["tenant"], execution_id=row["execution_id"],
        session_id=row["session_id"], kind=row["kind"], text=row["text"],
        tool=row["tool"], at=row["at"],
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
        next_attempt_at=row["next_attempt_at"],
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
        attempt=row["attempt"],
        next_attempt_at=row["next_attempt_at"],
    )


def _row_to_dead_letter(row: Any) -> DeadLetter:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return DeadLetter(
        id=row["id"],
        tenant=row["tenant"],
        source=row["source"],
        ref_id=row["ref_id"],
        kind=row["kind"],
        payload=payload,
        error=row["error"],
        attempts=row["attempts"],
        created_at=row["created_at"],
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
        self,
        tenant: str,
        now: datetime,
        lease_seconds: int,
        *,
        agent: str | None = None,
        wip_limit: int = 0,
    ) -> Run | None:
        lease_until = now + timedelta(seconds=lease_seconds)
        async with self._pool.acquire() as conn, conn.transaction():
            # WIP limit / backpressure (J): cap global de runs ATIVOS por tenant. Atingiu → não pega
            # novo (fica QUEUED até abrir vaga). 0 = sem limite. Evita pilha de review a jusante.
            if wip_limit > 0:
                active = await conn.fetchval(
                    "SELECT COUNT(*) FROM run WHERE tenant = $1 "
                    "AND state IN ('running', 'waiting', 'verifying')",
                    tenant,
                )
                if int(active or 0) >= wip_limit:
                    return None
            # concurrency-lock por (tenant, issue) (#165): advisory xact lock impede dois workers de
            # pegarem runs da MESMA issue em paralelo; o NOT EXISTS pula issues com irmão ativo
            # (running/waiting/verifying). Juntos serializam por entidade, sem travar outras.
            picked = await conn.fetchrow(
                """
                SELECT r.id, r.issue_id FROM run r
                WHERE r.tenant = $1 AND r.state = 'queued' AND ($2::text IS NULL OR r.agent = $2)
                  AND (r.next_attempt_at IS NULL OR r.next_attempt_at <= $3)
                  AND NOT EXISTS (
                      SELECT 1 FROM run s
                      WHERE s.tenant = r.tenant AND s.issue_id = r.issue_id
                        AND s.state IN ('running', 'waiting', 'verifying')
                  )
                  AND pg_try_advisory_xact_lock(hashtext(r.tenant || ':' || r.issue_id))
                ORDER BY r.id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                tenant, agent, now,
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

    async def defer_effect(
        self, effect_id: int, attempt: int, next_attempt_at: datetime, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE outbox SET attempt = $2, next_attempt_at = $3 WHERE id = $1",
                effect_id, attempt, next_attempt_at,
            )

    async def dead_letter_effect(self, effect_id: int, error: str, now: datetime) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "UPDATE outbox SET status = 'dead' WHERE id = $1 "
                "RETURNING tenant, kind, payload, dedup_key, attempt",
                effect_id,
            )
            if row is None:
                return
            raw = row["payload"]
            payload = raw if isinstance(raw, str) else json.dumps(raw)
            await conn.execute(
                """
                INSERT INTO dead_letter (tenant, source, ref_id, kind, payload, error, attempts,
                                         created_at)
                VALUES ($1, 'effect', $2, $3, $4::jsonb, $5, $6, $7)
                """,
                row["tenant"], effect_id, row["kind"], payload, error, row["attempt"] + 1, now,
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

    async def requeue_run_with_backoff(
        self, run_id: int, attempt: int, next_attempt_at: datetime, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE run SET state = 'queued', attempt = $2, lease_until = NULL,
                    next_attempt_at = $3, updated_at = $4
                WHERE id = $1
                """,
                run_id, attempt, next_attempt_at, now,
            )

    async def dead_letter_run(self, run_id: int, error: str, now: datetime) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "UPDATE run SET state = 'failed', lease_until = NULL, updated_at = $2 "
                "WHERE id = $1 RETURNING tenant, agent, repo, issue_id, attempt",
                run_id, now,
            )
            if row is None:
                return
            payload = json.dumps({"repo": row["repo"], "issue_id": row["issue_id"]})
            await conn.execute(
                """
                INSERT INTO dead_letter (tenant, source, ref_id, kind, payload, error, attempts,
                                         created_at)
                VALUES ($1, 'run', $2, $3, $4::jsonb, $5, $6, $7)
                """,
                row["tenant"], run_id, row["agent"], payload, error, row["attempt"], now,
            )

    async def list_dead_letter(self, tenant: str) -> list[DeadLetter]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_DEAD_LETTER_COLS} FROM dead_letter WHERE tenant = $1 ORDER BY id DESC",
                tenant,
            )
            return [_row_to_dead_letter(r) for r in rows]

    async def replay_dead_letter(self, dead_letter_id: int, now: datetime) -> bool:
        async with self._pool.acquire() as conn, conn.transaction():
            dl = await conn.fetchrow(
                "SELECT source, ref_id FROM dead_letter WHERE id = $1", dead_letter_id
            )
            if dl is None:
                return False
            if dl["source"] == "effect":
                await conn.execute(
                    "UPDATE outbox SET status = 'pending', attempt = 0, next_attempt_at = NULL, "
                    "sent_at = NULL WHERE id = $1",
                    dl["ref_id"],
                )
            else:
                await conn.execute(
                    "UPDATE run SET state = 'queued', attempt = 0, lease_until = NULL, "
                    "next_attempt_at = NULL, updated_at = $2 WHERE id = $1",
                    dl["ref_id"], now,
                )
            await conn.execute("DELETE FROM dead_letter WHERE id = $1", dead_letter_id)
            return True

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

    async def get_interaction(self, interaction_id: int) -> Interaction | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_INTERACTION_COLS} FROM interaction WHERE id = $1", interaction_id
            )
            return _row_to_interaction(row) if row is not None else None

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

    async def set_execution_pr(
        self, execution_id: int, number: int, url: str, diff: str, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO execution_pr (execution_id, number, url, diff, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (execution_id) DO UPDATE
                    SET number = $2, url = $3, diff = $4, updated_at = $5
                """,
                execution_id, number, url, diff, now,
            )

    async def get_execution_pr(self, execution_id: int) -> ExecutionPr | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT execution_id, number, url, diff, updated_at "
                "FROM execution_pr WHERE execution_id = $1",
                execution_id,
            )
            if row is None:
                return None
            return ExecutionPr(
                execution_id=row["execution_id"], number=row["number"], url=row["url"],
                diff=row["diff"], updated_at=row["updated_at"],
            )

    async def get_breakdown_draft(self, tenant: str, repo: str, issue_id: str) -> str | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT items_json FROM breakdown_draft "
                "WHERE tenant = $1 AND repo = $2 AND issue_id = $3",
                tenant, repo, issue_id,
            )
        return None if row is None else str(row["items_json"])

    async def set_breakdown_draft(
        self, tenant: str, repo: str, issue_id: str, items_json: str, now: datetime
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO breakdown_draft (tenant, repo, issue_id, items_json, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tenant, repo, issue_id) DO UPDATE
                    SET items_json = $4, updated_at = $5
                """,
                tenant, repo, issue_id, items_json, now,
            )

    async def delete_breakdown_draft(self, tenant: str, repo: str, issue_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM breakdown_draft WHERE tenant = $1 AND repo = $2 AND issue_id = $3",
                tenant, repo, issue_id,
            )

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

    async def spend_since(self, tenant: str, since: datetime) -> float:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_call "
                "WHERE tenant = $1 AND at >= $2",
                tenant, since,
            )
            return float(row["c"])

    async def count_runs_by_state(self, tenant: str) -> dict[str, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT state, COUNT(*) AS n FROM run WHERE tenant = $1 GROUP BY state",
                tenant,
            )
            return {r["state"]: int(r["n"]) for r in rows}

    async def cost_for_execution(self, execution_id: int) -> tuple[int, float]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(tokens_in + tokens_out), 0) AS tok, "
                "COALESCE(SUM(cost_usd), 0) AS cost FROM llm_call WHERE run_id = $1",
                execution_id,
            )
            return int(row["tok"]), float(row["cost"])

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

    async def get_pr_state(self, tenant: str, repo: str, pr_number: int) -> PrState | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_seen_sha, last_activity_at, reviewed_sha FROM pr_review_state "
                "WHERE tenant = $1 AND repo = $2 AND pr_number = $3",
                tenant, repo, pr_number,
            )
        if row is None:
            return None
        return PrState(
            last_seen_sha=row["last_seen_sha"],
            last_activity_at=row["last_activity_at"],
            reviewed_sha=row["reviewed_sha"],
        )

    async def set_pr_state(
        self, tenant: str, repo: str, pr_number: int, state: PrState
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pr_review_state
                    (tenant, repo, pr_number, last_seen_sha, last_activity_at, reviewed_sha)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (tenant, repo, pr_number) DO UPDATE SET
                    last_seen_sha = $4, last_activity_at = $5, reviewed_sha = $6
                """,
                tenant, repo, pr_number,
                state.last_seen_sha, state.last_activity_at, state.reviewed_sha,
            )

    async def get_app_config(self) -> dict[str, str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM app_config")
            return {r["key"]: r["value"] for r in rows}

    async def set_app_config(self, values: dict[str, str], now: datetime) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            for key, value in values.items():
                await conn.execute(
                    """
                    INSERT INTO app_config (key, value, updated_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = $3
                    """,
                    key, value, now,
                )

    async def append_session_event(
        self,
        tenant: str,
        execution_id: int,
        kind: str,
        now: datetime,
        *,
        text: str = "",
        tool: str = "",
        session_id: int | None = None,
    ) -> SessionEvent:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO session_event (tenant, execution_id, session_id, kind, text, tool, at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, tenant, execution_id, session_id, kind, text, tool, at
                """,
                tenant, execution_id, session_id, kind, text, tool, now,
            )
            return _row_to_session_event(row)

    async def session_events(
        self, execution_id: int, after_id: int, limit: int
    ) -> list[SessionEvent]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, tenant, execution_id, session_id, kind, text, tool, at "
                "FROM session_event WHERE execution_id = $1 AND id > $2 ORDER BY id LIMIT $3",
                execution_id, after_id, limit,
            )
            return [_row_to_session_event(r) for r in rows]

    async def tool_counts_for_execution(self, execution_id: int) -> dict[str, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tool, COUNT(*) AS n FROM session_event "
                "WHERE execution_id = $1 AND kind = 'tool_call' AND tool <> '' GROUP BY tool",
                execution_id,
            )
            return {r["tool"]: int(r["n"]) for r in rows}
