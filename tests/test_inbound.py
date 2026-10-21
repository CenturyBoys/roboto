"""Dispatch de inbound: comandos (list/pick), reply, e nova ideia (refino)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.human import request_human_input
from roboto.app.inbound import InboundOutcome, dispatch_inbound
from roboto.channels.model import InboundMessage, MessageKind
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.model import Error, GithubEvent, InteractionKind, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok, Result

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


_ISSUE_BODY = (
    "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] z\n## DoD\n- [ ] ci"
)


class _FakeLister:
    def __init__(self) -> None:
        self.updated: list[tuple[int, str]] = []

    async def list_open_issues(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str]], Error]:
        return Ok([(1, "primeira"), (2, "segunda")])

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        return Ok((f"feat: issue {number}", _ISSUE_BODY))


class _SeqGW:
    """Gateway que devolve respostas em sequência (um complete por vez)."""

    def __init__(self, replies: list[str]) -> None:
        self._r = replies

    async def complete(self, messages, tier):  # type: ignore[no-untyped-def]
        from roboto.llm.port import Completion

        return Ok(Completion(text=self._r.pop(0), model="stub", tokens_in=0, tokens_out=0))


async def _dispatch(  # type: ignore[no-untyped-def]
    store: InMemoryStore, msg: InboundMessage, github: object = None
):
    return await dispatch_inbound(
        msg, repo="acme/app", gateway=StubModelGateway(), transcriber=StubTranscriber(),
        store=store, now=_T0, github=github,  # type: ignore[arg-type]
    )


async def test_new_message_refines() -> None:
    store = InMemoryStore()
    out = await _dispatch(store, _msg("quero uma feature"))
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.REFINED
    assert len(await store.pending_effects(10)) == 1  # D30: propõe (pergunta), não cria sozinho


async def test_approval_ok_creates_issue() -> None:
    # D30: refino propõe; humano responde "ok" em reply -> AÍ a issue é enfileirada
    store = InMemoryStore()
    await _dispatch(store, _msg("quero uma feature", mid="1"))
    inter = (await store.pending_interactions("acme", 10))[0]
    await store.set_interaction_message_id(inter.id, "900")  # pergunta "enviada"
    out = await _dispatch(store, _msg("ok", reply_to="900", mid="2"))
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.CREATED
    effects = await store.pending_effects(10)
    assert any(e.kind == "create_issue" for e in effects)


async def test_conversation_asks_then_proposes() -> None:
    # Inc 2: ideia vaga -> Potter PERGUNTA; humano responde em reply -> Potter PROPÕE
    store = InMemoryStore()
    draft = (
        "TITLE: feat: placar\nBODY:\n## Contexto\nx\n## Escopo\ny\n"
        "## Critérios de aceite\n- [ ] z\n## DoD\n- [ ] ci\n## Fora de escopo\nnada"
    )
    gw = _SeqGW(["PERGUNTA: qual o escopo e os critérios?", draft, "VEREDITO: aprovado"])

    async def _disp(m: InboundMessage):  # type: ignore[no-untyped-def]
        return await dispatch_inbound(
            m, repo="acme/app", gateway=gw, transcriber=StubTranscriber(),  # type: ignore[arg-type]
            store=store, now=_T0,
        )

    out1 = await _disp(_msg("quero um placar", mid="1"))
    assert isinstance(out1, Ok) and out1.value.outcome is InboundOutcome.REFINED
    q = (await store.pending_interactions("acme", 10))[0]
    assert q.kind is InteractionKind.QUESTION  # pediu mais info
    await store.set_interaction_message_id(q.id, "900")

    out2 = await _disp(_msg("escopo auth, critério: entra", reply_to="900", mid="2"))
    assert isinstance(out2, Ok) and out2.value.outcome is InboundOutcome.REFINED
    pend = await store.pending_interactions("acme", 10)
    assert any(i.kind is InteractionKind.APPROVAL for i in pend)  # agora PROPÕE


async def test_greeting_returns_help_not_refine() -> None:
    # saudação/"ajuda" -> guia (sem LLM, sem run); conserta o "ola" que virava issue-lixo
    store = InMemoryStore()
    out = await _dispatch(store, _msg("ola", mid="1"))
    assert isinstance(out, Ok)
    assert out.value.reply is not None and "Potter" in out.value.reply
    assert len(store._runs) == 0  # NÃO virou refino/issue


async def test_discuss_existing_issue_proposes_edit_not_create() -> None:
    # "sobre a #180" -> ABRE trazendo os detalhes (pergunta); reply -> propõe; "ok" -> EDITA (D30)
    store = InMemoryStore()
    out = await _dispatch(store, _msg("sobre a issue 180", mid="1"), github=_FakeLister())
    assert isinstance(out, Ok) and out.value.outcome is InboundOutcome.DISCUSSING
    opening = (await store.pending_interactions("acme", 10))[0]
    assert opening.kind is InteractionKind.QUESTION and "#180" in opening.prompt  # trouxe detalhes
    await store.set_interaction_message_id(opening.id, "900")

    m2 = _msg("ajusta o DoD", reply_to="900", mid="2")
    out2 = await _dispatch(store, m2, github=_FakeLister())
    assert isinstance(out2, Ok) and out2.value.outcome is InboundOutcome.REFINED
    appr = next(
        i for i in await store.pending_interactions("acme", 10)
        if i.kind is InteractionKind.APPROVAL
    )
    await store.set_interaction_message_id(appr.id, "901")

    out3 = await _dispatch(store, _msg("ok", reply_to="901", mid="3"), github=_FakeLister())
    assert isinstance(out3, Ok) and out3.value.outcome is InboundOutcome.EDITED
    effects = await store.pending_effects(10)
    assert any(e.kind == "update_issue" and e.payload["number"] == "180" for e in effects)
    assert not any(e.kind == "create_issue" for e in effects)


async def test_approval_decline_does_not_create() -> None:
    store = InMemoryStore()
    await _dispatch(store, _msg("quero uma feature", mid="1"))
    inter = (await store.pending_interactions("acme", 10))[0]
    await store.set_interaction_message_id(inter.id, "900")
    out = await _dispatch(store, _msg("não, muda o escopo antes", reply_to="900", mid="2"))
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.DECLINED
    effects = await store.pending_effects(10)
    assert not any(e.kind == "create_issue" for e in effects)


async def test_pick_command_enqueues_run() -> None:
    store = InMemoryStore()
    out = await _dispatch(store, _msg("pega #42"))
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.PICKED
    assert "#42" in (out.value.reply or "")
    assert [r.issue_id for r in store._runs.values()] == ["42"]  # run enfileirado p/ a issue 42


async def test_repick_resumes_stopped_run() -> None:
    # re-pegar uma issue parada (waiting, ex.: completou o DoR) retoma o MESMO run -> queued (D30)
    store = InMemoryStore()
    await _dispatch(store, _msg("pega #42"))
    run_id = next(iter(store._runs))
    await store.set_state(run_id, RunState.WAITING, _T0)
    out = await _dispatch(store, _msg("pega #42"))
    assert isinstance(out, Ok)
    assert len(store._runs) == 1  # dedup: não cria run novo
    assert store._runs[run_id].state is RunState.QUEUED  # retomado
    assert "Retomando" in (out.value.reply or "")


async def test_list_command_lists_open_issues() -> None:
    store = InMemoryStore()
    out = await _dispatch(store, _msg("issues"), github=_FakeLister())
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.LISTED
    assert "#1 primeira" in (out.value.reply or "")


async def test_reply_to_known_interaction_answers() -> None:
    store = InMemoryStore()
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="1", agent="impl", idempotency_key="k"
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    req = await request_human_input(
        store, tenant="acme", execution_id=run.id, chat_id="5",
        kind=InteractionKind.DECISION, prompt="Redis ou DB?", options=["Redis", "DB"], now=_T0,
    )
    assert isinstance(req, Ok)
    await store.set_interaction_message_id(req.value.id, "777")
    out = await _dispatch(store, _msg("1, com abstração", reply_to="777", mid="900"))
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.ANSWERED


async def test_reply_to_unknown_is_unrouted() -> None:
    store = InMemoryStore()
    out = await _dispatch(store, _msg("1", reply_to="999", mid="901"))
    assert isinstance(out, Ok)
    assert out.value.outcome is InboundOutcome.UNROUTED
    assert "reply" in (out.value.reply or "")
