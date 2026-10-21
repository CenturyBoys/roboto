"""Publishers concretos do outbox: traduzem um OutboxItem em efeito real.

Ligam o núcleo (porta ``Publisher``) aos adapters (GitHub App, canal Telegram). Idempotência vem
do dedup_key no outbox + idempotência do destino; aqui só efetuamos.
"""

from __future__ import annotations

from roboto.channels.model import OutboundMessage
from roboto.channels.port import Channel
from roboto.github.app import GithubAppClient
from roboto.orchestrator.model import Error, OutboxItem
from roboto.orchestrator.store import Store
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


class GithubIssueUpdater:
    """Efeito ``update_issue`` (D30) -> edita o corpo da issue + comenta a trilha (quem/por quê)."""

    def __init__(self, client: GithubAppClient) -> None:
        self._client = client

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        p = item.payload
        number = int(p["number"])
        upd = await self._client.update_issue(
            str(p["repo"]), number, title=str(p["title"]), body=str(p["body"])
        )
        if isinstance(upd, Err):
            return Err(upd.error)
        note = str(p.get("note") or "")
        if note:  # 1 comentário de trilha (invariante D30: toda edição deixa rastro)
            await self._client.comment_pr(str(p["repo"]), number, note)
        return Ok(None)


class TelegramPublisher:
    """Efeito ``telegram_notify`` -> envia mensagem pelo canal (descarta o message_id)."""

    def __init__(self, channel: Channel) -> None:
        self._channel = channel

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        p = item.payload
        sent = await self._channel.send(
            OutboundMessage(chat_id=str(p["chat_id"]), text=str(p["text"]))
        )
        if isinstance(sent, Err):
            return Err(sent.error)
        return Ok(None)


class TelegramQuestionPublisher:
    """Efeito ``telegram_question`` -> envia a pergunta e **guarda o message_id** na interação.

    É o que torna o roteamento por reply possível (D24): a resposta em reply a essa mensagem
    localiza a interação pelo id do canal.
    """

    def __init__(self, channel: Channel, store: Store) -> None:
        self._channel = channel
        self._store = store

    async def send(self, item: OutboxItem) -> Result[None, Error]:
        p = item.payload
        sent = await self._channel.send(
            OutboundMessage(chat_id=str(p["chat_id"]), text=str(p["text"]))
        )
        if isinstance(sent, Err):
            return Err(sent.error)
        await self._store.set_interaction_message_id(int(p["interaction_id"]), sent.value)
        return Ok(None)
