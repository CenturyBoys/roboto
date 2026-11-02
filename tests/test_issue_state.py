"""Máquina de estados da issue -> label (Trilha A, #161): mapeamento puro + projeção."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.issue_state import issue_state_label, project_issue_labels_tick
from roboto.orchestrator.model import GithubEvent, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_mapping_basics() -> None:
    assert issue_state_label("impl", RunState.RUNNING) == "status:in-progress"
    assert issue_state_label("impl", RunState.VERIFYING) == "status:in-review"
    assert issue_state_label("refine", RunState.DONE) == "status:to-do"
    assert issue_state_label("correct", RunState.VERIFYING) == "status:in-review"
    assert issue_state_label("impl", RunState.DONE) == "status:done"
    assert issue_state_label("impl", RunState.WAITING) == "status:blocked"
    assert issue_state_label("impl", RunState.FAILED) == "status:blocked"
    assert issue_state_label("triage", RunState.QUEUED) is None


class _FakeGH:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str]] = []

    async def set_issue_state_label(self, repo: str, number: int, label: str):  # type: ignore[no-untyped-def]
        self.calls.append((repo, number, label))
        return Ok(None)


async def _mk(store: InMemoryStore, agent: str, state: RunState, *, key: str) -> None:
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="7", agent=agent, idempotency_key=key
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    await store.set_state(run.id, state, _T0)


async def test_tick_projects_and_dedupes() -> None:
    store = InMemoryStore()
    await _mk(store, "impl", RunState.VERIFYING, key="k")
    gh, seen = _FakeGH(), {}
    await project_issue_labels_tick(gh, store, tenant="acme", now=lambda: _T0, seen=seen)
    assert gh.calls == [("acme/app", 7, "status:in-review")]
    # 2ª passada, mesmo estado -> dedup (sem nova chamada à API)
    await project_issue_labels_tick(gh, store, tenant="acme", now=lambda: _T0, seen=seen)
    assert len(gh.calls) == 1


async def test_tick_latest_run_wins() -> None:
    store = InMemoryStore()
    await _mk(store, "refine", RunState.DONE, key="k1")  # run mais antigo
    await _mk(store, "impl", RunState.RUNNING, key="k2")  # run mais recente (mesma issue)
    gh = _FakeGH()
    await project_issue_labels_tick(gh, store, tenant="acme", now=lambda: _T0, seen={})
    assert gh.calls == [("acme/app", 7, "status:in-progress")]
