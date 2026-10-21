"""Issue escaneada pelo motor (scope): motor lê o repo -> rascunho -> proposta (determinístico)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.inbound import dispatch_inbound
from roboto.app.scope import process_scope_tick
from roboto.channels.model import InboundMessage, MessageKind
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.llm.stub import StubModelGateway, StubTranscriber
from roboto.orchestrator.model import GithubEvent, InteractionKind
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_DRAFT = (
    "TITLE: feat: rate limit\nBODY:\n## Contexto\nx\n## Escopo\npackages/core\n"
    "## Critérios de aceite\n- [ ] bloqueia acima de N\n## DoD\n- [ ] ci"
)


def _msg(text: str, mid: str = "1") -> InboundMessage:
    return InboundMessage(
        tenant="acme", chat_id="5", user_id="u1", kind=MessageKind.TEXT, text=text, message_id=mid
    )


async def test_new_idea_with_engine_scope_enqueues_scope_run() -> None:
    store = InMemoryStore()
    out = await dispatch_inbound(
        _msg("quero rate limit"), repo="acme/app", gateway=StubModelGateway(),
        transcriber=StubTranscriber(), store=store, now=_T0, engine_scope=True,
    )
    assert isinstance(out, Ok)
    runs = list(store._runs.values())
    assert len(runs) == 1 and runs[0].agent == "scope"  # virou run de scope, não chat
    effects = await store.pending_effects(10)
    assert any("Explorando" in e.payload.get("text", "") for e in effects)  # ack


async def test_scope_tick_motor_monta_e_propoe() -> None:
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="scope:5:1", agent="scope",
        idempotency_key="k", origin_chat_id="5",
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    seed = await store.create_interaction(
        "acme", run.id, InteractionKind.QUESTION, "IDEIA_INICIAL", [], _T0
    )
    await store.answer_interaction(seed.id, "quero rate limit", "u1", _T0)
    engine = StubEngine([
        EngineEvent(EngineEventKind.MESSAGE, text=_DRAFT),
        EngineEvent(EngineEventKind.FINISHED, tokens_in=500, tokens_out=100),
    ])
    await process_scope_tick(engine, store, tenant="acme", workdir_root="/work", now=lambda: _T0)
    # sessão do motor + custo medidos
    assert len(await store.sessions_for_execution(run.id)) == 1
    calls = await store.llm_calls("acme", 10)
    assert sum(c.tokens_in + c.tokens_out for c in calls) == 600
    # PROPÕE: interação APPROVAL com o rascunho do motor + pergunta no outbox
    appr = [i for i in await store.pending_interactions("acme", 10)
            if i.kind is InteractionKind.APPROVAL]
    assert len(appr) == 1 and appr[0].options[0] == "feat: rate limit"
    assert any(e.kind == "telegram_question" for e in await store.pending_effects(10))
