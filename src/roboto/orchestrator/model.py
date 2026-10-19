"""Modelo do orquestrador (ver docs/design/orquestrador.md). Schema real = migrations/."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class RunState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class GithubEvent:
    """Evento já normalizado (o transporte/validação de assinatura fica fora deste núcleo)."""

    tenant: str
    repo: str
    issue_id: str
    agent: str
    idempotency_key: str


@dataclass(frozen=True)
class Run:
    id: int
    tenant: str
    repo: str
    issue_id: str
    agent: str
    state: RunState
    attempt: int
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    lease_until: datetime | None = None


@dataclass(frozen=True)
class OutboxItem:
    id: int
    tenant: str
    run_id: int
    kind: str
    payload: dict[str, Any]
    dedup_key: str
    status: str
    created_at: datetime
    sent_at: datetime | None = None


@dataclass(frozen=True)
class Error:
    """Erro como valor (D1). ``kind`` ∈ db | dispatch | effect | invalid_signature."""

    kind: str
    message: str = ""
