"""Modelo do orquestrador (ver docs/design/orquestrador.md). Schema real = migrations/."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RunState(StrEnum):
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
    origin_chat_id: str | None = None  # chat do Telegram que originou (feedback volta pra lá, D30)


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
    origin_chat_id: str | None = None  # origem p/ ecoar status/pergunta no Telegram (D30)


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


class Engine(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"


class InteractionKind(StrEnum):
    QUESTION = "question"
    DECISION = "decision"
    APPROVAL = "approval"


class InteractionStatus(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Session:
    """Sessão de trabalho de um motor de coding para uma execução (=run). D23."""

    id: int
    tenant: str
    execution_id: int
    engine: Engine
    state: str
    created_at: datetime
    updated_at: datetime
    native_session_id: str | None = None


@dataclass(frozen=True)
class Interaction:
    """Pergunta/decisão humana pendente (request_human_input — D24)."""

    id: int
    tenant: str
    execution_id: int
    kind: InteractionKind
    prompt: str
    options: list[str]
    status: InteractionStatus
    created_at: datetime
    session_id: int | None = None
    channel_message_id: str | None = None
    answer: str | None = None
    answered_by: str | None = None
    expires_at: datetime | None = None
    answered_at: datetime | None = None


@dataclass(frozen=True)
class LlmCall:
    """Registro de uso de modelo (D10/L) — tokens/custo por run, p/ medir economia (F)."""

    id: int
    tenant: str
    run_id: int | None
    model: str
    tier: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    at: datetime


@dataclass(frozen=True)
class Error:
    """Erro como valor (D1). ``kind`` ∈ db | dispatch | effect | invalid_signature."""

    kind: str
    message: str = ""
