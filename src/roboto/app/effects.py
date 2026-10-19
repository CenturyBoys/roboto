"""Publishers concretos do outbox: traduzem um OutboxItem em efeito real.

Ligam o núcleo (porta ``Publisher``) aos adapters (GitHub App, canal Telegram). Idempotência vem
do dedup_key no outbox + idempotência do destino; aqui só efetuamos.
"""

from __future__ import annotations

from roboto.channels.model import OutboundMessage
from roboto.channels.port import Channel
from roboto.github.app import GithubAppClient
from roboto.orchestrator.model import Error, OutboxItem
from roboto.result import Err, Ok, Result


class GithubIssuePublisher:
    """Efeito ``create_issue`` -> abre a issue (materializa o rascunho; verdade no GitHub)."""

    def __init__(self, client: GithubAppClient) -> None:
        self._client = client

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        p = item.payload
        result = await self._client.create_issue(
            repo=str(p["repo"]), title=str(p["title"]), body=str(p["body"])
        )
        if isinstance(result, Err):
            return Err(result.error)
        return Ok(None)


class TelegramPublisher:
    """Efeito ``telegram_notify`` -> envia mensagem pelo canal."""

    def __init__(self, channel: Channel) -> None:
        self._channel = channel

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        p = item.payload
        return await self._channel.send(
            OutboundMessage(chat_id=str(p["chat_id"]), text=str(p["text"]))
        )
