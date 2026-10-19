"""Porta do gateway de modelos (escada de validação: judge/cheap/frontier — I/L).

O núcleo chama ``ModelGateway`` por interface; o provedor real (OpenRouter) e os stubs de teste
implementam esta porta. STT é a porta ``Transcriber`` (áudio -> texto).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from roboto.orchestrator.model import Error
from roboto.result import Result


class Tier(StrEnum):
    JUDGE = "judge"
    CHEAP = "cheap"
    FRONTIER = "frontier"


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class ModelGateway(Protocol):
    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]: ...


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, filename: str) -> Result[str, Error]: ...
