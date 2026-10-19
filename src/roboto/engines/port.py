"""Contrato comum do motor de coding (D22, Trilha N §3).

Um `CodingEngine` é o adapter de um motor externo (Claude Code, Codex) que executa a implementação
no container efêmero. É **diferente** do `ModelGateway` (chamada primitiva de LLM): o motor tem
sessão própria, usa ferramentas, faz perguntas, pede aprovação e **retoma**. O contrato aqui é o
mínimo comum que ambos atendem (ver `capabilities.py` para o que é nativo vs. suprido pelo host).

O host (orquestrador) consome `events()`; quando o motor precisa de decisão humana, o evento vira
uma `interaction` (D24) e a execução entra em `WAITING`; a resposta volta por `respond()` ou por um
novo `start(resume_session_id=...)`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from roboto.orchestrator.model import Engine, Error
from roboto.result import Result


@dataclass(frozen=True)
class RunSpec:
    tenant: str
    repo: str
    workdir: str
    prompt: str
    model: str = ""
    resume_session_id: str | None = None  # retoma uma sessão nativa (sobrevive a restart)


class EngineEventKind(StrEnum):
    MESSAGE = "message"  # texto do assistente
    TOOL_CALL = "tool_call"  # ferramenta/comando executado (auditoria)
    NEEDS_APPROVAL = "needs_approval"  # host precisa allow/deny uma ação
    NEEDS_INPUT = "needs_input"  # motor pede decisão/esclarecimento humano
    FINISHED = "finished"  # turno/execução concluído
    FAILED = "failed"  # erro terminal


@dataclass(frozen=True)
class EngineEvent:
    kind: EngineEventKind
    text: str = ""  # mensagem / pergunta / resumo da ação
    options: list[str] = field(default_factory=list)  # alternativas (NEEDS_INPUT/decisão)
    tool: str = ""  # ferramenta/comando (TOOL_CALL/NEEDS_APPROVAL)
    tokens_in: int = 0
    tokens_out: int = 0


class CodingEngine(Protocol):
    @property
    def engine(self) -> Engine: ...

    async def start(self, spec: RunSpec) -> Result[str, Error]:
        """Inicia (ou retoma) a execução; retorna o id da sessão NATIVA do motor (D23)."""
        ...

    def events(self) -> AsyncIterator[EngineEvent]:
        """Stream dos eventos do motor até precisar de humano, terminar ou falhar."""
        ...

    async def respond(self, answer: str) -> Result[None, Error]:
        """Entrega uma resposta humana ao turno em espera (steer / nova mensagem)."""
        ...

    async def interrupt(self) -> Result[None, Error]:
        """Interrompe a execução em andamento (cancelamento)."""
        ...
