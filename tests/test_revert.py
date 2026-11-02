"""Recuperação git-first (Trilha H): process_revert_tick reverte o PR e reabre a issue."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.revert import process_revert_tick
from roboto.orchestrator.model import GithubEvent, RunState
from roboto.orchestrator.store import InMemoryStore
from test_pr_cycle import _FakeGit, _FakeGithub

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_revert_run(store: InMemoryStore, *, pr: int | None = 42) -> int:
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="7", agent="revert", idempotency_key="rev"
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    if pr is not None:  # o endpoint liga o PR a reverter ao run de revert
        await store.set_execution_pr(run.id, pr, f"url/{pr}", "diff", _T0)
    return run.id


async def test_revert_opens_revert_pr_and_reopens_issue() -> None:
    store = InMemoryStore()
    run_id = await _seed_revert_run(store, pr=42)
    git, github = _FakeGit(), _FakeGithub()
    await process_revert_tick(
        github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work",
        git_factory=lambda ws: git, now=lambda: _T0,
    )
    assert len(git.reverts) == 1  # reverteu os commits do PR
    assert git.pushes == ["revert/run-" + str(run_id)]  # empurrou a branch de revert
    assert github.opened == 1  # abriu o PR de revert
    assert (7, "open") in github.issue_states  # reabriu a issue #7
    assert store._runs[run_id].state is RunState.DONE  # type: ignore[attr-defined]


async def test_revert_conflict_fails_without_push() -> None:
    store = InMemoryStore()
    run_id = await _seed_revert_run(store, pr=42)
    git, github = _FakeGit(), _FakeGithub()
    git.revert_ok = False  # simula conflito no git revert
    await process_revert_tick(
        github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work",
        git_factory=lambda ws: git, now=lambda: _T0,
    )
    assert git.pushes == []  # NÃO empurrou nada quebrado
    assert github.opened == 0  # não abriu PR
    assert store._runs[run_id].state is RunState.FAILED  # type: ignore[attr-defined]


async def test_revert_without_linked_pr_fails() -> None:
    store = InMemoryStore()
    run_id = await _seed_revert_run(store, pr=None)  # sem PR ligado
    git, github = _FakeGit(), _FakeGithub()
    await process_revert_tick(
        github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work",
        git_factory=lambda ws: git, now=lambda: _T0,
    )
    assert store._runs[run_id].state is RunState.FAILED  # type: ignore[attr-defined]
    assert git.reverts == []
