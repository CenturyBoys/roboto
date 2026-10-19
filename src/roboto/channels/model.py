"""Mensagens de canal — núcleo agnóstico (D20).

O canal (Telegram, CLI, ...) é um adapter que traduz para estes tipos. Áudio vira ``bytes`` já
baixados pelo adapter; a transcrição (STT) acontece no núcleo via porta ``Transcriber``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MessageKind(StrEnum):
    TEXT = "text"
    AUDIO = "audio"


@dataclass(frozen=True)
class InboundMessage:
    """Mensagem recebida de um humano, já autorizada pelo transporte (allowlist — Trilha M)."""

    tenant: str
    chat_id: str
    user_id: str
    kind: MessageKind
    text: str = ""
    audio: bytes | None = None
    audio_name: str | None = None


@dataclass(frozen=True)
class OutboundMessage:
    chat_id: str
    text: str
