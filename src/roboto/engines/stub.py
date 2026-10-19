"""StubEngine determinístico — roda o loop interativo sem motor/rede real (testes tier-1).

Scripta uma sequência de `EngineEvent`. O driver (`app.engine_loop`) consome até precisar de
humano / terminar / falhar. Permite desenvolver e testar o loop antes do PoC dos motores reais.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from roboto.engines.port import EngineEvent, RunSpec
from roboto.orchestrator.model import Engine, Error
from roboto.result import Ok, Result


class StubEngine:
    def __init__(
        self,
        script: list[EngineEvent],
        *,
        engine: Engine = Engine.CLAUDE_CODE,
        native_session_id: str = "stub-session",
    ) -> None:
        self._script = script
        self._engine = engine
        self._native = native_session_id
        self.started: list[RunSpec] = []
        self.responses: list[str] = []
        self.interrupted = False

    @property
    def engine(self) -> Engine:
        return self._engine

    async def start(self, spec: RunSpec) -> Result[str, Error]:
        self.started.append(spec)
        return Ok(spec.resume_session_id or self._native)

    async def events(self) -> AsyncIterator[EngineEvent]:
        for event in self._script:
            yield event

    async def respond(self, answer: str) -> Result[None, Error]:
        self.responses.append(answer)
        return Ok(None)

    async def interrupt(self) -> Result[None, Error]:
        self.interrupted = True
        return Ok(None)
