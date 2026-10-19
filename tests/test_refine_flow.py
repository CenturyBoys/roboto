"""Fluxo refino -> outbox (determinístico, InMemoryStore + stubs)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.refine import refine_to_issue
from roboto.channels.model import InboundMessage, MessageKind
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.model import RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _msg(text: str, message_id: str = "11") -> InboundMessage:
    return InboundMessage(
        tenant="acme",
        chat_id="5",
        user_id="u1",
        kind=MessageKind.TEXT,
        text=text,
        message_id=message_id,
    )


async def _refine(store: InMemoryStore, msg: InboundMessage, reply: str = "TITLE: X\nBODY: y"):  # type: ignore[no-untyped-def]
    return await refine_to_issue(
        msg,
        repo="acme/app",
        gateway=StubModelGateway(reply=reply),
        transcriber=StubTranscriber(),
        store=store,
        now=_T0,
    )


async def test_refine_enqueues_issue_and_ack() -> None:
    store = InMemoryStore()
    result = await _refine(store, _msg("arruma o login"), reply="TITLE: Login\nBODY: corpo")
    assert isinstance(result, Ok)
    assert store._runs[result.value.id].state is RunState.VERIFYING
    effects = await store.pending_effects(10)
    assert {e.kind for e in effects} == {"create_issue", "telegram_notify"}
    issue = next(e for e in effects if e.kind == "create_issue")
    assert issue.payload == {"repo": "acme/app", "title": "Login", "body": "corpo"}


async def test_refine_dedups_duplicate_message() -> None:
    store = InMemoryStore()
    first = await _refine(store, _msg("oi", "11"))
    second = await _refine(store, _msg("oi", "11"))  # mesmo message_id
    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert second.value.id == first.value.id
    assert len(await store.pending_effects(10)) == 2  # não duplica efeitos


async def test_refine_empty_text_fails_run_without_effects() -> None:
    store = InMemoryStore()
    result = await _refine(store, _msg("   ", "9"))
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"
    assert [r.state for r in store._runs.values()] == [RunState.FAILED]
    assert await store.pending_effects(10) == []
