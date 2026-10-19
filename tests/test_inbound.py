"""Dispatch de inbound: reply (roteado/não-roteado) vs. nova solicitação de refino."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.human import request_human_input
from roboto.app.inbound import InboundOutcome, dispatch_inbound
from roboto.channels.model import InboundMessage, MessageKind
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.model import GithubEvent, InteractionKind
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _msg(text: str, *, reply_to: str | None = None, mid: str = "1") -> InboundMessage:
    return InboundMessage(
        tenant="acme",
        chat_id="5",
        user_id="u1",
        kind=MessageKind.TEXT,
        text=text,
        message_id=mid,
        reply_to_message_id=reply_to,
    )


async def _dispatch(store: InMemoryStore, msg: InboundMessage):  # type: ignore[no-untyped-def]
    return await dispatch_inbound(
        msg,
        repo="acme/app",
        gateway=StubModelGateway(),
        transcriber=StubTranscriber(),
        store=store,
        now=_T0,
    )


async def test_new_message_refines() -> None:
    store = InMemoryStore()
    out = await _dispatch(store, _msg("quero uma feature"))
    assert isinstance(out, Ok)
    assert out.value is InboundOutcome.REFINED
    assert len(await store.pending_effects(10)) == 2  # create_issue + ack


async def test_reply_to_known_interaction_answers() -> None:
    store = InMemoryStore()
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="1", agent="impl", idempotency_key="k"
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    req = await request_human_input(
        store,
        tenant="acme",
        execution_id=run.id,
        chat_id="5",
        kind=InteractionKind.DECISION,
        prompt="Redis ou DB?",
        options=["Redis", "DB"],
        now=_T0,
    )
    assert isinstance(req, Ok)
    await store.set_interaction_message_id(req.value.id, "777")
    out = await _dispatch(store, _msg("1, com abstração", reply_to="777", mid="900"))
    assert isinstance(out, Ok)
    assert out.value is InboundOutcome.ANSWERED


async def test_reply_to_unknown_is_unrouted() -> None:
    store = InMemoryStore()
    out = await _dispatch(store, _msg("1", reply_to="999", mid="901"))
    assert isinstance(out, Ok)
    assert out.value is InboundOutcome.UNROUTED
