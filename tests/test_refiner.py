"""Tier-1 do agente de Refinamento — determinístico, com stubs (sem rede)."""

from __future__ import annotations

from roboto.agents.refiner import handle_inbound, refine
from roboto.channels.model import InboundMessage, MessageKind
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.result import Err, Ok


def _text_msg(text: str) -> InboundMessage:
    return InboundMessage(
        tenant="acme", chat_id="100", user_id="u1", kind=MessageKind.TEXT, text=text
    )


async def test_refine_parses_title_and_body() -> None:
    gw = StubModelGateway(reply="TITLE: Corrigir login\nBODY: usuário não entra\ncritério: entra")
    result = await refine("o login não funciona", gw)
    assert isinstance(result, Ok)
    assert result.value.title == "Corrigir login"
    assert "usuário não entra" in result.value.body
    assert "critério: entra" in result.value.body


async def test_handle_text_produces_draft_and_ack() -> None:
    gw = StubModelGateway(reply="TITLE: Nova feature\nBODY: detalhes")
    result = await handle_inbound(_text_msg("quero uma feature"), gw, StubTranscriber())
    assert isinstance(result, Ok)
    assert result.value.draft.title == "Nova feature"
    assert result.value.ack.chat_id == "100"
    assert "Nova feature" in result.value.ack.text
    assert result.value.transcript == "quero uma feature"


async def test_handle_audio_transcribes_then_refines() -> None:
    gw = StubModelGateway(reply="TITLE: Do áudio\nBODY: corpo")
    tr = StubTranscriber(transcript="corrige o fluxo de pagamento")
    msg = InboundMessage(
        tenant="acme", chat_id="7", user_id="u1", kind=MessageKind.AUDIO, audio=b"\x01\x02"
    )
    result = await handle_inbound(msg, gw, tr)
    assert isinstance(result, Ok)
    assert result.value.transcript == "corrige o fluxo de pagamento"
    assert result.value.draft.title == "Do áudio"


async def test_empty_text_is_err() -> None:
    result = await handle_inbound(_text_msg("   "), StubModelGateway(), StubTranscriber())
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"


async def test_audio_without_bytes_is_err() -> None:
    msg = InboundMessage(tenant="acme", chat_id="7", user_id="u1", kind=MessageKind.AUDIO)
    result = await handle_inbound(msg, StubModelGateway(), StubTranscriber())
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"


async def test_parse_fallback_without_markers() -> None:
    gw = StubModelGateway(reply="só uma linha solta sem marcadores")
    result = await refine("algo", gw)
    assert isinstance(result, Ok)
    assert result.value.title == "só uma linha solta sem marcadores"
