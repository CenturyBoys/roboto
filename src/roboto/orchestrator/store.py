"""Porta de armazenamento + implementação em memória (MVP/testes, sem Postgres).

O ``InMemoryStore`` é determinístico e single-thread (async). A versão Postgres implementa a
mesma ``Store`` depois — a troca é por interface (determinismo primeiro).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from roboto.orchestrator.model import GithubEvent, OutboxItem, Run, RunState


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


class InMemoryStore:
    """Store em memória para testes tier-1 e o MVP local."""

    def __init__(self) -> None:
        self._runs: dict[int, Run] = {}
        self._run_by_key: dict[tuple[str, str], int] = {}
        self._effects: dict[int, OutboxItem] = {}
        self._effect_keys: set[tuple[str, str]] = set()
        self._run_seq = 0
        self._effect_seq = 0

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
