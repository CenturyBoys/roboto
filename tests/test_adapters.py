"""Adapters reais (Telegram / OpenRouter / STT) exercitados via httpx.MockTransport.

Sem rede (determinístico, roda no CI): injeta um transport fake no AsyncClient e valida o
parsing/rotas de cada adapter — inclusive allowlist e download de voz do Telegram.
"""

from __future__ import annotations

import httpx

from roboto.channels.model import MessageKind, OutboundMessage
from roboto.channels.telegram import TelegramChannel
from roboto.llm.openrouter import OpenRouterGateway
from roboto.llm.port import ChatMessage, Tier
from roboto.llm.stt import WhisperTranscriber
from roboto.result import Ok


def _client(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_openrouter_parses_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "model": "deepseek/deepseek-chat",
                "choices": [{"message": {"content": "TITLE: X\nBODY: y"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5},
            },
        )

    client = _client(handler)
    try:
        gw = OpenRouterGateway("sk-test", client=client)
        result = await gw.complete([ChatMessage("user", "oi")], Tier.CHEAP)
        assert isinstance(result, Ok)
        assert result.value.text == "TITLE: X\nBODY: y"
        assert result.value.tokens_in == 3
        assert result.value.tokens_out == 5
    finally:
        await client.aclose()


async def test_whisper_returns_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/transcriptions")
        return httpx.Response(200, json={"text": "olá mundo"})

    client = _client(handler)
    try:
        stt = WhisperTranscriber("sk-test", client=client)
        result = await stt.transcribe(b"\x01\x02", "voice.ogg")
        assert isinstance(result, Ok)
        assert result.value == "olá mundo"
    finally:
        await client.aclose()


async def test_telegram_poll_allowlist_and_voice_download() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/getUpdates"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "update_id": 10,
                            "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "oi"},
                        },
                        {
                            "update_id": 11,
                            "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "x"},
                        },
                        {
                            "update_id": 12,
                            "message": {
                                "from": {"id": 111},
                                "chat": {"id": 111},
                                "voice": {"file_id": "f1"},
                            },
                        },
                    ]
                },
            )
        if path.endswith("/getFile"):
            return httpx.Response(200, json={"result": {"file_path": "voice/file_1.ogg"}})
        if "/file/bot" in path:
            return httpx.Response(200, content=b"\x00\x01\x02")
        return httpx.Response(404)

    client = _client(handler)
    try:
        ch = TelegramChannel("tok", "acme", allowlist={"111"}, client=client)
        result = await ch.poll()
        assert isinstance(result, Ok)
        msgs = result.value
        # intruso (999) filtrado pela allowlist -> sobram texto + voz
        assert len(msgs) == 2
        assert msgs[0].kind is MessageKind.TEXT
        assert msgs[0].text == "oi"
        assert msgs[1].kind is MessageKind.AUDIO
        assert msgs[1].audio == b"\x00\x01\x02"
        assert ch._offset == 13  # cursor avançou além do maior update_id
    finally:
        await client.aclose()


async def test_telegram_send_returns_message_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sendMessage")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 987}})

    client = _client(handler)
    try:
        ch = TelegramChannel("tok", "acme", allowlist=set(), client=client)
        result = await ch.send(OutboundMessage(chat_id="1", text="oi"))
        assert isinstance(result, Ok)
        assert result.value == "987"
    finally:
        await client.aclose()


async def test_telegram_poll_captures_reply_to() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 50,
                            "from": {"id": 111},
                            "chat": {"id": 111},
                            "text": "2",
                            "reply_to_message": {"message_id": 42},
                        },
                    }
                ]
            },
        )

    client = _client(handler)
    try:
        ch = TelegramChannel("tok", "acme", allowlist={"111"}, client=client)
        result = await ch.poll()
        assert isinstance(result, Ok)
        assert result.value[0].reply_to_message_id == "42"
    finally:
        await client.aclose()
