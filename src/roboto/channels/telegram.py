"""Adapter real do Telegram (canal humano primário, D20).

long-poll (getUpdates) com cursor de offset; voz (.ogg) é baixada para bytes e marcada AUDIO
(o STT roda no núcleo). Allowlist de user IDs é aplicada AQUI (finding alto da Trilha M): o
transporte autentica quem fala antes de a mensagem entrar no núcleo. Mutação de estado continua
revalidada no servidor a jusante — um toque no chat não aprova nada sozinho.
"""

from __future__ import annotations

from typing import Any

import httpx

from roboto.channels.model import InboundMessage, MessageKind, OutboundMessage
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class TelegramChannel:
    def __init__(
        self,
        token: str,
        tenant: str,
        *,
        allowlist: set[str],
        api_base: str = "https://api.telegram.org",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token
        self._tenant = tenant
        self._allow = allowlist
        self._api = f"{api_base}/bot{token}"
        self._file_api = f"{api_base}/file/bot{token}"
        self._client = client
        self._timeout = timeout
        self._offset = 0

    @property
    def cursor(self) -> str | None:
        return str(self._offset) if self._offset else None

    @cursor.setter
    def cursor(self, value: str | None) -> None:
        self._offset = int(value) if value else 0

    async def poll(self) -> Result[list[InboundMessage], Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            resp = await client.get(
                f"{self._api}/getUpdates", params={"offset": self._offset, "timeout": 0}
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])
            out: list[InboundMessage] = []
            for upd in updates:
                self._offset = max(self._offset, int(upd["update_id"]) + 1)
                parsed = await self._parse(upd, client)
                if parsed is not None:
                    out.append(parsed)
            return Ok(out)
        except httpx.HTTPError as exc:
            return Err(Error("channel", f"telegram getUpdates: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def send(self, msg: OutboundMessage) -> Result[str, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            resp = await client.post(
                f"{self._api}/sendMessage", json={"chat_id": msg.chat_id, "text": msg.text}
            )
            resp.raise_for_status()
            return Ok(str(resp.json()["result"]["message_id"]))
        except httpx.HTTPError as exc:
            return Err(Error("channel", f"telegram sendMessage: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def _parse(self, upd: Any, client: httpx.AsyncClient) -> InboundMessage | None:
        message = upd.get("message")
        if message is None:
            return None
        user_id = str(message.get("from", {}).get("id", ""))
        if user_id not in self._allow:  # allowlist (Trilha M)
            return None
        chat_id = str(message["chat"]["id"])
        message_id = str(message.get("message_id", ""))
        reply_to = message.get("reply_to_message")
        reply_to_message_id = (
            str(reply_to["message_id"]) if isinstance(reply_to, dict) else None
        )
        if "voice" in message:
            audio = await self._download(message["voice"]["file_id"], client)
            return InboundMessage(
                tenant=self._tenant,
                chat_id=chat_id,
                user_id=user_id,
                kind=MessageKind.AUDIO,
                message_id=message_id,
                audio=audio,
                audio_name="voice.ogg",
            )
        if "text" in message:
            return InboundMessage(
                tenant=self._tenant,
                chat_id=chat_id,
                user_id=user_id,
                kind=MessageKind.TEXT,
                message_id=message_id,
                reply_to_message_id=reply_to_message_id,
                text=str(message["text"]),
            )
        return None

    async def _download(self, file_id: str, client: httpx.AsyncClient) -> bytes:
        meta = await client.get(f"{self._api}/getFile", params={"file_id": file_id})
        meta.raise_for_status()
        path = meta.json()["result"]["file_path"]
        blob = await client.get(f"{self._file_api}/{path}")
        blob.raise_for_status()
        return blob.content
