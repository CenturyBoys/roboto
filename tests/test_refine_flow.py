"""Fluxo refino -> gate de prontidão (DoR) -> outbox (determinístico, InMemoryStore + stubs)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.refine import refine_to_issue
from roboto.channels.model import InboundMessage, MessageKind
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.model import RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)

# issue COMPLETA (passa o gate DoR): seções + critério de aceite; "aprovado" p/ o juiz semântico
_READY = (
    "VEREDITO: aprovado\nTITLE: Login\nBODY:\n## Contexto\nusuário não entra\n## Escopo\napp/auth\n"
    "## Critérios de aceite\n- [ ] usuário entra\n## DoD\n- [ ] testes + CI\n"
    "## Fora de escopo\nnada"
)


def _msg(text: str, message_id: str = "11") -> InboundMessage:
    return InboundMessage(
        tenant="acme",
        chat_id="5",
        user_id="u1",
        kind=MessageKind.TEXT,
        text=text,
        message_id=message_id,
    )


async def _refine(  # type: ignore[no-untyped-def]
    store: InMemoryStore, msg: InboundMessage, reply: str | None = None
):
    gateway = StubModelGateway() if reply is None else StubModelGateway(reply=reply)
    return await refine_to_issue(
        msg, repo="acme/app", gateway=gateway, transcriber=StubTranscriber(), store=store, now=_T0
    )


async def test_refine_ready_issue_proposes_and_waits() -> None:
    store = InMemoryStore()
    result = await _refine(store, _msg("arruma o login"), reply=_READY)
    assert isinstance(result, Ok)
    # D30: NÃO cria sozinho — propõe o rascunho e espera o OK (WAITING + pergunta no Telegram)
    assert store._runs[result.value.id].state is RunState.WAITING
    effects = await store.pending_effects(10)
    assert [e.kind for e in effects] == ["telegram_question"]
    assert "Proponho" in effects[0].payload["text"]
    # rascunho guardado na interação (options=[title, body]) p/ materializar no OK
    inter = (await store.pending_interactions("acme", 10))[0]
    assert inter.options[0] == "Login"
    assert "## Critérios de aceite" in inter.options[1]
    # medição: refiner + juiz semântico, ambos gravados no llm_call
    assert len(await store.llm_calls("acme", 10)) == 2


async def test_refine_semantic_reject_asks_clarification() -> None:
    store = InMemoryStore()
    # estruturalmente OK (todas as seções + '- [ ]'), mas o juiz REPROVA -> pede ajuste, sem issue
    reply = (
        "VEREDITO: reprovado\n- critério de aceite vago demais\n"
        "TITLE: algo\nBODY:\n## Contexto\nx\n## Escopo\ny\n"
        "## Critérios de aceite\n- [ ] faz\n## DoD\n- [ ] ci"
    )
    result = await _refine(store, _msg("faz um negocio ai", "77"), reply=reply)
    assert isinstance(result, Ok)
    assert store._runs[result.value.id].state is RunState.WAITING
    effects = await store.pending_effects(10)
    assert [e.kind for e in effects] == ["telegram_notify"]
    assert "ajuste" in effects[0].payload["text"].lower()


async def test_refine_incomplete_issue_asks_clarification() -> None:
    store = InMemoryStore()
    result = await _refine(store, _msg("faz algo"), reply="TITLE: X\nBODY: só uma linha")
    assert isinstance(result, Ok)
    # gate barrou: execução em espera, SEM create_issue — só o pedido de esclarecimento
    assert store._runs[result.value.id].state is RunState.WAITING
    effects = await store.pending_effects(10)
    assert [e.kind for e in effects] == ["telegram_notify"]
    assert "incompleta" in effects[0].payload["text"].lower()


async def test_refine_dedups_duplicate_message() -> None:
    store = InMemoryStore()
    first = await _refine(store, _msg("oi", "11"))
    second = await _refine(store, _msg("oi", "11"))  # mesmo message_id
    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert second.value.id == first.value.id
    assert len(await store.pending_effects(10)) == 1  # 1 proposta, não duplica no update repetido


async def test_refine_empty_text_fails_run_without_effects() -> None:
    store = InMemoryStore()
    result = await _refine(store, _msg("   ", "9"))
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"
    assert [r.state for r in store._runs.values()] == [RunState.FAILED]
    assert await store.pending_effects(10) == []
