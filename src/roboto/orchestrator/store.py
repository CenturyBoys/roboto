"""Porta de armazenamento + implementação em memória (MVP/testes, sem Postgres).

O ``InMemoryStore`` é determinístico e single-thread (async). A versão Postgres implementa a
mesma ``Store`` depois — a troca é por interface (determinismo primeiro).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Protocol

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

# estados em que uma issue está "sendo trabalhada" — base do concurrency-lock por entidade (#165).
_ACTIVE_STATES = frozenset({RunState.RUNNING, RunState.WAITING, RunState.VERIFYING})


class Store(Protocol):
    async def insert_run_if_absent(self, ev: GithubEvent, now: datetime) -> tuple[Run, bool]: ...

    async def claim_next_queued(
        self, tenant: str, now: datetime, lease_seconds: int, *, agent: str | None = None
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

    async def defer_effect(
        self, effect_id: int, attempt: int, next_attempt_at: datetime, now: datetime
    ) -> None: ...

    async def dead_letter_effect(self, effect_id: int, error: str, now: datetime) -> None: ...

    async def find_abandoned(self, now: datetime) -> list[Run]: ...

    async def dead_letter_run(self, run_id: int, error: str, now: datetime) -> None: ...

    async def requeue_run_with_backoff(
        self, run_id: int, attempt: int, next_attempt_at: datetime, now: datetime
    ) -> None: ...

    async def list_dead_letter(self, tenant: str) -> list[DeadLetter]: ...

    async def replay_dead_letter(self, dead_letter_id: int, now: datetime) -> bool: ...

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

    async def get_interaction(self, interaction_id: int) -> Interaction | None: ...

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

    async def cost_for_execution(self, execution_id: int) -> tuple[int, float]: ...

    async def get_channel_offset(self, tenant: str, channel: str) -> int | None: ...

    async def set_channel_offset(
        self, tenant: str, channel: str, offset: int, now: datetime
    ) -> None: ...

    async def get_pr_state(self, tenant: str, repo: str, pr_number: int) -> PrState | None: ...

    async def set_pr_state(
        self, tenant: str, repo: str, pr_number: int, state: PrState
    ) -> None: ...

    async def remember(
        self, tenant: str, text: str, *, kind: str, ref: str, now: datetime
    ) -> MemoryFact: ...

    async def recall(self, tenant: str, query: str, limit: int) -> list[MemoryFact]: ...

    async def get_app_config(self) -> dict[str, str]: ...

    async def set_app_config(self, values: dict[str, str], now: datetime) -> None: ...

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
    ) -> SessionEvent: ...

    async def session_events(
        self, execution_id: int, after_id: int, limit: int
    ) -> list[SessionEvent]: ...

    async def set_execution_pr(
        self, execution_id: int, number: int, url: str, diff: str, now: datetime
    ) -> None: ...

    async def get_execution_pr(self, execution_id: int) -> ExecutionPr | None: ...


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
        self._pr_state: dict[tuple[str, str, int], PrState] = {}
        self._facts: list[MemoryFact] = []
        self._app_config: dict[str, str] = {}
        self._session_events: list[SessionEvent] = []
        self._execution_prs: dict[int, ExecutionPr] = {}
        self._dead_letters: dict[int, DeadLetter] = {}
        self._dl_seq = 0
        self._fact_seq = 0
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
        self, tenant: str, now: datetime, lease_seconds: int, *, agent: str | None = None
    ) -> Run | None:
        # concurrency-lock por (tenant, issue): no máximo 1 run ATIVO por entidade (#165). Dois
        # eventos da mesma issue não rodam em paralelo — o 2º espera o 1º sair do estado ativo.
        busy = {
            (r.tenant, r.issue_id) for r in self._runs.values() if r.state in _ACTIVE_STATES
        }
        for run_id in sorted(self._runs):
            run = self._runs[run_id]
            if (
                run.tenant == tenant
                and run.state == RunState.QUEUED
                and (agent is None or run.agent == agent)
                and (run.next_attempt_at is None or run.next_attempt_at <= now)  # backoff
                and (run.tenant, run.issue_id) not in busy  # concurrency-lock por entidade
            ):
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

    async def defer_effect(
        self, effect_id: int, attempt: int, next_attempt_at: datetime, now: datetime
    ) -> None:
        item = self._effects[effect_id]
        self._effects[effect_id] = replace(item, attempt=attempt, next_attempt_at=next_attempt_at)

    async def dead_letter_effect(self, effect_id: int, error: str, now: datetime) -> None:
        item = self._effects[effect_id]
        self._effects[effect_id] = replace(item, status="dead")
        self._dl_seq += 1
        self._dead_letters[self._dl_seq] = DeadLetter(
            id=self._dl_seq, tenant=item.tenant, source="effect", ref_id=item.id, kind=item.kind,
            payload=item.payload, error=error, attempts=item.attempt + 1, created_at=now,
        )

    async def find_abandoned(self, now: datetime) -> list[Run]:
        return [
            r
            for r in self._runs.values()
            if r.state == RunState.RUNNING and r.lease_until is not None and r.lease_until < now
        ]

    async def dead_letter_run(self, run_id: int, error: str, now: datetime) -> None:
        run = self._runs[run_id]
        self._runs[run_id] = replace(run, state=RunState.FAILED, lease_until=None, updated_at=now)
        self._dl_seq += 1
        self._dead_letters[self._dl_seq] = DeadLetter(
            id=self._dl_seq, tenant=run.tenant, source="run", ref_id=run.id, kind=run.agent,
            payload={"repo": run.repo, "issue_id": run.issue_id}, error=error,
            attempts=run.attempt, created_at=now,
        )

    async def requeue_run_with_backoff(
        self, run_id: int, attempt: int, next_attempt_at: datetime, now: datetime
    ) -> None:
        run = self._runs[run_id]
        self._runs[run_id] = replace(
            run, state=RunState.QUEUED, attempt=attempt, lease_until=None,
            next_attempt_at=next_attempt_at, updated_at=now,
        )

    async def list_dead_letter(self, tenant: str) -> list[DeadLetter]:
        return [d for d in self._dead_letters.values() if d.tenant == tenant]

    async def replay_dead_letter(self, dead_letter_id: int, now: datetime) -> bool:
        dl = self._dead_letters.get(dead_letter_id)
        if dl is None:
            return False
        if dl.source == "effect":
            item = self._effects[dl.ref_id]
            self._effects[dl.ref_id] = replace(
                item, status="pending", attempt=0, next_attempt_at=None, sent_at=None
            )
        else:  # run
            run = self._runs[dl.ref_id]
            self._runs[dl.ref_id] = replace(
                run, state=RunState.QUEUED, attempt=0, lease_until=None,
                next_attempt_at=None, updated_at=now,
            )
        del self._dead_letters[dead_letter_id]
        return True

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

    async def get_interaction(self, interaction_id: int) -> Interaction | None:
        return self._interactions.get(interaction_id)

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

    async def set_execution_pr(
        self, execution_id: int, number: int, url: str, diff: str, now: datetime
    ) -> None:
        self._execution_prs[execution_id] = ExecutionPr(
            execution_id=execution_id, number=number, url=url, diff=diff, updated_at=now
        )

    async def get_execution_pr(self, execution_id: int) -> ExecutionPr | None:
        return self._execution_prs.get(execution_id)

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

    async def cost_for_execution(self, execution_id: int) -> tuple[int, float]:
        calls = [c for c in self._llm_calls if c.run_id == execution_id]
        return sum(c.tokens_in + c.tokens_out for c in calls), sum(c.cost_usd for c in calls)

    async def get_channel_offset(self, tenant: str, channel: str) -> int | None:
        return self._channel_cursor.get((tenant, channel))

    async def set_channel_offset(
        self, tenant: str, channel: str, offset: int, now: datetime
    ) -> None:
        self._channel_cursor[(tenant, channel)] = offset

    async def get_pr_state(self, tenant: str, repo: str, pr_number: int) -> PrState | None:
        return self._pr_state.get((tenant, repo, pr_number))

    async def set_pr_state(
        self, tenant: str, repo: str, pr_number: int, state: PrState
    ) -> None:
        self._pr_state[(tenant, repo, pr_number)] = state

    async def remember(
        self, tenant: str, text: str, *, kind: str, ref: str, now: datetime
    ) -> MemoryFact:
        self._fact_seq += 1
        fact = MemoryFact(
            id=self._fact_seq, tenant=tenant, kind=kind, ref=ref, text=text, created_at=now
        )
        self._facts.append(fact)
        return fact

    async def recall(self, tenant: str, query: str, limit: int) -> list[MemoryFact]:
        terms = [t for t in query.lower().split() if len(t) > 2]
        scored: list[tuple[int, MemoryFact]] = []
        for f in self._facts:
            if f.tenant != tenant:
                continue
            low = f.text.lower()
            score = sum(low.count(t) for t in terms)
            if score:
                scored.append((score, f))
        scored.sort(key=lambda x: (-x[0], -x[1].id))
        return [f for _, f in scored[:limit]]

    async def get_app_config(self) -> dict[str, str]:
        return dict(self._app_config)

    async def set_app_config(self, values: dict[str, str], now: datetime) -> None:
        self._app_config.update(values)

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
        event = SessionEvent(
            id=len(self._session_events) + 1,
            tenant=tenant,
            execution_id=execution_id,
            kind=kind,
            text=text,
            tool=tool,
            at=now,
            session_id=session_id,
        )
        self._session_events.append(event)
        return event

    async def session_events(
        self, execution_id: int, after_id: int, limit: int
    ) -> list[SessionEvent]:
        items = [
            e
            for e in self._session_events
            if e.execution_id == execution_id and e.id > after_id
        ]
        return items[:limit]
