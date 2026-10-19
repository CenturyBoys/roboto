"""Portas de execução (runner) e de efeito (publisher do outbox) + stubs de MVP/teste."""

from __future__ import annotations

from typing import Protocol

from roboto.orchestrator.model import Error, OutboxItem, Run
from roboto.result import Err, Ok, Result


class Runner(Protocol):
    async def dispatch(self, run: Run) -> Result[None, Error]: ...


class Publisher(Protocol):
    async def send(self, item: OutboxItem) -> Result[None, Error]: ...


class StubRunner:
    """Runner de MVP/teste: registra os runs disparados (não executa agente ainda)."""

    def __init__(self) -> None:
        self.dispatched: list[Run] = []

    async def dispatch(self, run: Run) -> Result[None, Error]:
        self.dispatched.append(run)
        return Ok(None)


class StubPublisher:
    """Publisher de MVP/teste: registra os efeitos efetuados."""

    def __init__(self) -> None:
        self.sent: list[OutboxItem] = []

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        self.sent.append(item)
        return Ok(None)


class RouterPublisher:
    """Despacha cada efeito ao Publisher registrado por ``kind`` (create_issue, telegram_notify).

    Mantém o ``publish_outbox`` genérico (determinismo primeiro): o núcleo não conhece os adapters;
    só este roteador liga ``kind -> handler``. Efeito sem handler vira ``Err`` (misconfig visível).
    """

    def __init__(self, handlers: dict[str, Publisher]) -> None:
        self._handlers = handlers

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        handler = self._handlers.get(item.kind)
        if handler is None:
            return Err(Error("effect", f"sem handler para kind={item.kind}"))
        return await handler.send(item)
