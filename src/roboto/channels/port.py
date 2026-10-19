"""Porta de canal: receber mensagens (inbound) e enviar (outbound)."""

from __future__ import annotations

from typing import Protocol

from roboto.channels.model import InboundMessage, OutboundMessage
from roboto.orchestrator.model import Error
from roboto.result import Result


class Channel(Protocol):
    async def poll(self) -> Result[list[InboundMessage], Error]:
        """Busca novas mensagens (long-poll/webhook drain). Avança o cursor internamente."""
        ...

    async def send(self, msg: OutboundMessage) -> Result[None, Error]: ...
