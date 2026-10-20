"""Porta de armazenamento + implementação em memória (MVP/testes, sem Postgres).

O ``InMemoryStore`` é determinístico e single-thread (async). A versão Postgres implementa a
mesma ``Store`` depois — a troca é por interface (determinismo primeiro).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from roboto.orchestrator.model import (
    Engine,
    GithubEvent,
    Interaction,
    InteractionKind,
    InteractionStatus,
    LlmCall,
    OutboxItem,
    Run,
    RunState,
    Session,
)


class Store(Protocol):
    async def insert_run_if_absent(self, ev: GithubEvent, now: datetime) -> tuple[Run, bool]: ...

    async def claim_next_queued(
        self, tenant: str, now: datetime, lease_seconds: int
    ) -> Run | None: ...

    async def set_state(
        self, run_id: int, state: RunState, now: datetime, attempt: int | None = None
    ) -> None: ...

    async def enqueue_effect(
        self,
        tenant: str,
        run_id: int,
        kind: str,
        payload: dict[str, Any],
        dedup_key: str,
        now: datetime,
    ) -> bool: ...

    async def pending_effects(self, limit: int) -> list[OutboxItem]: ...

    async def mark_sent(self, effect_id: int, now: datetime) -> None: ...

    async def find_abandoned(self, now: datetime) -> list[Run]: ...

    async def create_session(
        self, tenant: str, execution_id: int, engine: Engine, now: datetime
    ) -> Session: ...

    async def set_native_session(
        self, session_id: int, native_session_id: str, now: datetime
    ) -> None: ...

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
    ) -> Interaction: ...

    async def set_interaction_message_id(
        self, interaction_id: int, channel_message_id: str
    ) -> None: ...

    async def get_interaction_by_message_id(
        self, tenant: str, channel_message_id: str
    ) -> Interaction | None: ...

    async def answer_interaction(
        self, interaction_id: int, answer: str, answered_by: str, now: datetime
    ) -> bool: ...

    async def pending_interactions(self, tenant: str, limit: int) -> list[Interaction]: ...

    async def list_runs(self, tenant: str, limit: int) -> list[Run]: ...

    async def get_run(self, run_id: int) -> Run | None: ...

    async def sessions_for_execution(self, execution_id: int) -> list[Session]: ...

    async def interactions_for_execution(self, execution_id: int) -> list[Interaction]: ...

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
    ) -> None: ...

    async def llm_calls(self, tenant: str, limit: int) -> list[LlmCall]: ...

    async def get_channel_offset(self, tenant: str, channel: str) -> int | None: ...

    async def set_channel_offset(
        self, tenant: str, channel: str, offset: int, now: datetime
    ) -> None: ...


class InMemoryStore:
    """Store em memória para testes tier-1 e o MVP local."""

    def __init__(self) -> None:
        self._runs: dict[int, Run] = {}
        self._run_by_key: dict[tuple[str, str], int] = {}
        self._effects: dict[int, OutboxItem] = {}
        self._effect_keys: set[tuple[str, str]] = set()
        self._sessions: dict[int, Session] = {}
        self._interactions: dict[int, Interaction] = {}
        self._interaction_by_msg: dict[tuple[str, str], int] = {}
        self._llm_calls: list[LlmCall] = []
        self._channel_cursor: dict[tuple[str, str], int] = {}
        self._run_seq = 0
        self._effect_seq = 0
        self._session_seq = 0
        self._interaction_seq = 0

    async def insert_run_if_absent(self, ev: GithubEvent, now: datetime) -> tuple[Run, bool]:
        key = (ev.tenant, ev.idempotency_key)
        existing = self._run_by_key.get(key)
        if existing is not None:
            return self._runs[existing], False
        self._run_seq += 1
        run = Run(
            id=self._run_seq,
            tenant=ev.tenant,
            repo=ev.repo,
            issue_id=ev.issue_id,
            agent=ev.agent,
            state=RunState.QUEUED,
            attempt=0,
            idempotency_key=ev.idempotency_key,
            created_at=now,
            updated_at=now,
            origin_chat_id=ev.origin_chat_id,
        )
        self._runs[run.id] = run
        self._run_by_key[key] = run.id
        return run, True

    async def claim_next_queued(
        self, tenant: str, now: datetime, lease_seconds: int
    ) -> Run | None:
        for run_id in sorted(self._runs):
            run = self._runs[run_id]
            if run.tenant == tenant and run.state == RunState.QUEUED:
                # lock + reconferir: transição atômica queued -> running
                claimed = replace(
                    run,
                    state=RunState.RUNNING,
                    lease_until=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
                self._runs[run_id] = claimed
                return claimed
        return None

    async def set_state(
        self, run_id: int, state: RunState, now: datetime, attempt: int | None = None
    ) -> None:
        run = self._runs[run_id]
        lease = run.lease_until if state == RunState.RUNNING else None
        self._runs[run_id] = replace(
            run,
            state=state,
            updated_at=now,
            attempt=run.attempt if attempt is None else attempt,
            lease_until=lease,
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
        key = (tenant, dedup_key)
        if key in self._effect_keys:
            return False
        self._effect_seq += 1
        self._effects[self._effect_seq] = OutboxItem(
            id=self._effect_seq,
            tenant=tenant,
            run_id=run_id,
            kind=kind,
            payload=payload,
            dedup_key=dedup_key,
            status="pending",
            created_at=now,
        )
        self._effect_keys.add(key)
        return True

    async def pending_effects(self, limit: int) -> list[OutboxItem]:
        pending = [
            self._effects[i] for i in sorted(self._effects) if self._effects[i].status == "pending"
        ]
        return pending[:limit]

    async def mark_sent(self, effect_id: int, now: datetime) -> None:
        item = self._effects[effect_id]
        self._effects[effect_id] = replace(item, status="sent", sent_at=now)

    async def find_abandoned(self, now: datetime) -> list[Run]:
        return [
            r
            for r in self._runs.values()
            if r.state == RunState.RUNNING and r.lease_until is not None and r.lease_until < now
        ]

    async def create_session(
        self, tenant: str, execution_id: int, engine: Engine, now: datetime
    ) -> Session:
        self._session_seq += 1
        session = Session(
            id=self._session_seq,
            tenant=tenant,
            execution_id=execution_id,
            engine=engine,
            state="active",
            created_at=now,
            updated_at=now,
        )
        self._sessions[session.id] = session
        return session

    async def set_native_session(
        self, session_id: int, native_session_id: str, now: datetime
    ) -> None:
        session = self._sessions[session_id]
        self._sessions[session_id] = replace(
            session, native_session_id=native_session_id, updated_at=now
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
        self._interaction_seq += 1
        interaction = Interaction(
            id=self._interaction_seq,
            tenant=tenant,
            execution_id=execution_id,
            kind=kind,
            prompt=prompt,
            options=list(options),
            status=InteractionStatus.PENDING,
            created_at=now,
            session_id=session_id,
            expires_at=expires_at,
        )
        self._interactions[interaction.id] = interaction
        return interaction

    async def set_interaction_message_id(
        self, interaction_id: int, channel_message_id: str
    ) -> None:
        interaction = self._interactions[interaction_id]
        self._interactions[interaction_id] = replace(
            interaction, channel_message_id=channel_message_id
        )
        self._interaction_by_msg[(interaction.tenant, channel_message_id)] = interaction_id

    async def get_interaction_by_message_id(
        self, tenant: str, channel_message_id: str
    ) -> Interaction | None:
        iid = self._interaction_by_msg.get((tenant, channel_message_id))
        return self._interactions[iid] if iid is not None else None

    async def answer_interaction(
        self, interaction_id: int, answer: str, answered_by: str, now: datetime
    ) -> bool:
        interaction = self._interactions[interaction_id]
        if interaction.status is not InteractionStatus.PENDING:
            return False  # 1ª resposta válida vence; demais rejeitadas (§6)
        self._interactions[interaction_id] = replace(
            interaction,
            status=InteractionStatus.ANSWERED,
            answer=answer,
            answered_by=answered_by,
            answered_at=now,
        )
        return True

    async def pending_interactions(self, tenant: str, limit: int) -> list[Interaction]:
        items = [
            self._interactions[i]
            for i in sorted(self._interactions)
            if self._interactions[i].tenant == tenant
            and self._interactions[i].status is InteractionStatus.PENDING
        ]
        return items[:limit]

    async def list_runs(self, tenant: str, limit: int) -> list[Run]:
        runs = [
            self._runs[i]
            for i in sorted(self._runs, reverse=True)
            if self._runs[i].tenant == tenant
        ]
        return runs[:limit]

    async def get_run(self, run_id: int) -> Run | None:
        return self._runs.get(run_id)

    async def sessions_for_execution(self, execution_id: int) -> list[Session]:
        return [
            self._sessions[i]
            for i in sorted(self._sessions)
            if self._sessions[i].execution_id == execution_id
        ]

    async def interactions_for_execution(self, execution_id: int) -> list[Interaction]:
        return [
            self._interactions[i]
            for i in sorted(self._interactions)
            if self._interactions[i].execution_id == execution_id
        ]

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
        self._llm_calls.append(
            LlmCall(
                id=len(self._llm_calls) + 1,
                tenant=tenant,
                run_id=run_id,
                model=model,
                tier=tier,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                at=now,
            )
        )

    async def llm_calls(self, tenant: str, limit: int) -> list[LlmCall]:
        return [c for c in self._llm_calls if c.tenant == tenant][:limit]

    async def get_channel_offset(self, tenant: str, channel: str) -> int | None:
        return self._channel_cursor.get((tenant, channel))

    async def set_channel_offset(
        self, tenant: str, channel: str, offset: int, now: datetime
    ) -> None:
        self._channel_cursor[(tenant, channel)] = offset
