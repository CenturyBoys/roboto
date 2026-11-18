"""Testes do enforcement de aprovação por ação (#265, app.approval_gate)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from roboto.app.approval_gate import (
    decide_tool_use,
    make_approval_callback,
    make_policy_callback,
    verify_and_decide,
)
from roboto.app.approval_guard import ApprovedAction
from roboto.app.policy import ActionKind, ActionMode, Autonomy, Policy
from roboto.app.session_hub import LiveSession
from roboto.orchestrator.model import InteractionKind, InteractionStatus
from roboto.orchestrator.store import InMemoryStore


def _now() -> datetime:
    return datetime(2026, 11, 18, tzinfo=UTC)


# --- verify_and_decide (puro: libera/nega sem I/O) -----------------------------------------


def test_verify_allows_matching_approval() -> None:
    signed = ApprovedAction.sign("Bash", {"command": "git status"})
    decision = verify_and_decide(signed, "Bash", {"command": "git status"}, approved=True)
    assert decision.allow


def test_verify_denies_when_human_refuses() -> None:
    signed = ApprovedAction.sign("Bash", {"command": "git push"})
    decision = verify_and_decide(signed, "Bash", {"command": "git push"}, approved=False)
    assert not decision.allow
    assert "negado" in decision.reason


def test_verify_denies_loopjacking_when_action_changed() -> None:
    # Humano aprovou `ls`, mas a ação a executar virou `rm -rf /` (estado mexido): NEGA.
    signed = ApprovedAction.sign("Bash", {"command": "ls"})
    decision = verify_and_decide(signed, "Bash", {"command": "rm -rf /"}, approved=True)
    assert not decision.allow
    assert "loopjacking" in decision.reason


# --- decide_tool_use (integra store + SessionHub) ------------------------------------------


async def _resolve_first_pending(
    store: InMemoryStore, live: LiveSession, tenant: str, *, approved: bool
) -> int:
    """Espera a interação de aprovação aparecer e entrega a decisão humana. Devolve o id."""
    for _ in range(100):
        pending = await store.pending_interactions(tenant, 10)
        if pending:
            live.resolve_approval(pending[0].id, approved)
            return pending[0].id
        await asyncio.sleep(0)
    raise AssertionError("interação de aprovação não apareceu")


async def test_decide_allows_and_persists_approval() -> None:
    store, live, tenant = InMemoryStore(), LiveSession(execution_id=1), "t1"
    task = asyncio.create_task(
        decide_tool_use(
            store=store,
            live=live,
            tenant=tenant,
            execution_id=1,
            tool="Bash",
            args={"command": "git status"},
            now=_now,
        )
    )
    interaction_id = await _resolve_first_pending(store, live, tenant, approved=True)
    decision = await task

    assert decision.allow
    interaction = await store.get_interaction(interaction_id)
    assert interaction is not None
    assert interaction.kind is InteractionKind.APPROVAL
    assert interaction.status is InteractionStatus.ANSWERED
    assert interaction.answer == "allow"


async def test_decide_denies_with_reason() -> None:
    store, live, tenant = InMemoryStore(), LiveSession(execution_id=2), "t1"
    task = asyncio.create_task(
        decide_tool_use(
            store=store,
            live=live,
            tenant=tenant,
            execution_id=2,
            tool="Bash",
            args={"command": "git push"},
            now=_now,
        )
    )
    interaction_id = await _resolve_first_pending(store, live, tenant, approved=False)
    decision = await task

    assert not decision.allow
    interaction = await store.get_interaction(interaction_id)
    assert interaction is not None
    assert interaction.answer is not None
    assert interaction.answer.startswith("deny")


async def test_make_callback_wires_a_run() -> None:
    store, live, tenant = InMemoryStore(), LiveSession(execution_id=3), "t1"
    approve = make_approval_callback(
        store=store, live=live, tenant=tenant, execution_id=3, now=_now
    )
    task = asyncio.create_task(approve("Write", {"file_path": "a.py"}))
    await _resolve_first_pending(store, live, tenant, approved=True)
    decision = await task
    assert decision.allow


# --- make_policy_callback: a policy decide auto/ask/off antes do humano (#267) -------------


async def test_policy_callback_auto_allows_without_human() -> None:
    store, live, tenant = InMemoryStore(), LiveSession(execution_id=4), "t1"
    gate = make_policy_callback(
        store=store, live=live, tenant=tenant, execution_id=4,
        policy=Policy(Autonomy.FREE), now=_now,
    )
    decision = await gate("Bash", {"command": "git commit -m x"})  # auto no FREE: sem interação
    assert decision.allow
    assert await store.pending_interactions(tenant, 10) == []


async def test_policy_callback_auto_denies_off_rule() -> None:
    store, live, tenant = InMemoryStore(), LiveSession(execution_id=5), "t1"
    policy = Policy(Autonomy.FREE, rules={ActionKind.PUSH: ActionMode.OFF})
    gate = make_policy_callback(
        store=store, live=live, tenant=tenant, execution_id=5, policy=policy, now=_now
    )
    decision = await gate("Bash", {"command": "git push"})
    assert not decision.allow
    assert await store.pending_interactions(tenant, 10) == []  # off nega sem perguntar


async def test_policy_callback_asks_human_on_merge() -> None:
    store, live, tenant = InMemoryStore(), LiveSession(execution_id=6), "t1"
    gate = make_policy_callback(
        store=store, live=live, tenant=tenant, execution_id=6,
        policy=Policy(Autonomy.FREE), now=_now,
    )
    task = asyncio.create_task(gate("Bash", {"command": "gh pr merge 1"}))  # merge sempre humano
    await _resolve_first_pending(store, live, tenant, approved=True)
    decision = await task
    assert decision.allow
