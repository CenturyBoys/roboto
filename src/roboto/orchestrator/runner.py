"""Portas de execução (runner) e de efeito (publisher do outbox) + stubs de MVP/teste."""

from __future__ import annotations

from typing import Protocol

from roboto.orchestrator.model import Error, OutboxItem, Run
from roboto.result import Ok, Result


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
