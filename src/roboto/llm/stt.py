"""Transcriber real (speech-to-text) via endpoint OpenAI-compatível (``/audio/transcriptions``).

Telegram manda voz (.ogg) -> adapter baixa bytes -> este STT devolve texto -> mesmo pipeline de
refino (D20). base_url/model configuráveis (Whisper em qualquer provedor compatível).
"""

from __future__ import annotations

import httpx

from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class WhisperTranscriber:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        model: str = "whisper-1",
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._model = model
        self._client = client
        self._timeout = timeout

    async def transcribe(self, audio: bytes, filename: str) -> Result[str, Error]:
        headers = {"Authorization": f"Bearer {self._key}"}
        files = {"file": (filename, audio, "application/octet-stream")}
        data = {"model": self._model}
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            resp = await client.post(
                f"{self._base}/audio/transcriptions", headers=headers, data=data, files=files
            )
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            return Err(Error("stt", f"transcribe: {exc}"))
        finally:
            if owns:
                await client.aclose()
        return Ok(str(body["text"]))
