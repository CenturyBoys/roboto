"""Stubs determinísticos do gateway/transcriber — testes tier-1 sem rede."""

from __future__ import annotations

from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class StubModelGateway:
    """Devolve sempre ``reply`` (ou um ``Err`` se construído com erro)."""

    def __init__(self, reply: str = "TITLE: Rascunho\nBODY: (sem corpo)") -> None:
        self._reply = reply

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        return Ok(Completion(text=self._reply, model="stub", tokens_in=0, tokens_out=0))


class StubTranscriber:
    def __init__(self, transcript: str = "texto transcrito") -> None:
        self._transcript = transcript

    async def transcribe(self, audio: bytes, filename: str) -> Result[str, Error]:
        if not audio:
            return Err(Error("invalid", "áudio vazio"))
        return Ok(self._transcript)
