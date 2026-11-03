"""Reconciliar VERIFYING contra o PR (merged→DONE, fechado→ABANDONED), cobrindo impl e correct."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.reconcile import reconcile_verifying
from roboto.orchestrator.model import Error, GithubEvent, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok, Result

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


class _Github:
    # merged: set de PRs mergeados; closed: set de PRs fechados (sem merge)
    def __init__(self, merged: set[int], closed: set[int]) -> None:
        self._merged = merged
        self._closed = closed

    async def pr_merged(self, repo: str, number: int) -> Result[bool, Error]:
        return Ok(number in self._merged)

    async def get_issue_state(self, repo: str, number: int) -> Result[str, Error]:
        return Ok("closed" if number in self._closed or number in self._merged else "open")


async def _verifying(store: InMemoryStore, agent: str, issue_id: str, key: str) -> int:
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id=issue_id, agent=agent, idempotency_key=key
    )
    r, _ = await store.insert_run_if_absent(ev, _T0)
    await store.set_state(r.id, RunState.VERIFYING, _T0)
    return r.id


async def test_correct_run_merged_closes_to_done() -> None:
    # o bug: run CORRECT (issue_id = nº do PR) não tinha execution_pr e travava. Agora fecha.
    store = InMemoryStore()
    rid = await _verifying(store, "correct", "238", "k1")
    n = await reconcile_verifying(store, _Github({238}, set()), tenant="acme", now=_T0)
    assert n == 1
    assert store._runs[rid].state is RunState.DONE  # type: ignore[attr-defined]


async def test_impl_run_merged_via_execution_pr() -> None:
    store = InMemoryStore()
    rid = await _verifying(store, "impl", "231", "k2")
    await store.set_execution_pr(rid, 238, "https://x/238", "diff", _T0)
    await reconcile_verifying(store, _Github({238}, set()), tenant="acme", now=_T0)
    assert store._runs[rid].state is RunState.DONE  # type: ignore[attr-defined]


async def test_closed_without_merge_abandons() -> None:
    store = InMemoryStore()
    rid = await _verifying(store, "correct", "999", "k3")
    await reconcile_verifying(store, _Github(set(), {999}), tenant="acme", now=_T0)
    assert store._runs[rid].state is RunState.ABANDONED  # type: ignore[attr-defined]


async def test_open_pr_stays_verifying() -> None:
    store = InMemoryStore()
    rid = await _verifying(store, "correct", "500", "k4")
    n = await reconcile_verifying(store, _Github(set(), set()), tenant="acme", now=_T0)
    assert n == 0
    assert store._runs[rid].state is RunState.VERIFYING  # type: ignore[attr-defined]


async def test_non_verifying_untouched() -> None:
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="238", agent="impl", idempotency_key="k5"
    )
    r, _ = await store.insert_run_if_absent(ev, _T0)  # fica QUEUED
    await reconcile_verifying(store, _Github({238}, set()), tenant="acme", now=_T0)
    assert store._runs[r.id].state is RunState.QUEUED  # type: ignore[attr-defined]
