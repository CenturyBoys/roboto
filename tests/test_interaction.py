"""Session + interaction no InMemoryStore (determinístico; base do D24)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.orchestrator.model import (
    Engine,
    GithubEvent,
    InteractionKind,
    InteractionStatus,
)
from roboto.orchestrator.store import InMemoryStore

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _event() -> GithubEvent:
    return GithubEvent(
        tenant="acme", repo="acme/app", issue_id="1", agent="impl", idempotency_key="k1"
    )


async def test_session_native_mapping() -> None:
    store = InMemoryStore()
    run, _ = await store.insert_run_if_absent(_event(), _T0)
    session = await store.create_session("acme", run.id, Engine.CODEX, _T0)
    assert session.native_session_id is None
    await store.set_native_session(session.id, "nat", _T0)
    assert store._sessions[session.id].native_session_id == "nat"


async def test_interaction_routing_and_first_wins() -> None:
    store = InMemoryStore()
    run, _ = await store.insert_run_if_absent(_event(), _T0)
    interaction = await store.create_interaction(
        "acme", run.id, InteractionKind.QUESTION, "qual persistência?", ["a", "b"], _T0
    )
    await store.set_interaction_message_id(interaction.id, "m1", _T0)

    found = await store.get_interaction_by_message_id("acme", "m1")
    assert found is not None
    assert found.id == interaction.id
    assert await store.get_interaction_by_message_id("acme", "nope") is None

    assert await store.answer_interaction(interaction.id, "a", "u1", _T0) is True
    assert await store.answer_interaction(interaction.id, "b", "u2", _T0) is False
    answered = store._interactions[interaction.id]
    assert answered.status is InteractionStatus.ANSWERED
    assert answered.answer == "a"
    assert answered.answered_by == "u1"
    assert await store.pending_interactions("acme", 10) == []
