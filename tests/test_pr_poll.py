"""Gatilho por polling de PR com debounce (Trilha B, #166) — lógica pura + tick com fakes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from roboto.app.pr_poll import decide_pr, process_pr_poll_tick
from roboto.orchestrator.model import PrState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_DB = timedelta(minutes=30)


def test_first_sight_records_no_dispatch() -> None:
    d = decide_pr(1, "sha1", None, _T0, _DB)
    assert d.dispatch is False
    assert d.new_state == PrState("sha1", _T0, "")


def test_commit_change_resets_debounce() -> None:
    prev = PrState("sha1", _T0, "")
    d = decide_pr(1, "sha2", prev, _T0 + timedelta(minutes=5), _DB)
    assert d.dispatch is False
    assert d.new_state.last_seen_sha == "sha2"
    assert d.new_state.last_activity_at == _T0 + timedelta(minutes=5)


def test_stable_past_debounce_dispatches() -> None:
    prev = PrState("sha1", _T0, "")
    d = decide_pr(1, "sha1", prev, _T0 + timedelta(minutes=31), _DB)
    assert d.dispatch is True
    assert d.new_state.reviewed_sha == "sha1"


def test_stable_within_debounce_waits() -> None:
    prev = PrState("sha1", _T0, "")
    d = decide_pr(1, "sha1", prev, _T0 + timedelta(minutes=10), _DB)
    assert d.dispatch is False


def test_already_reviewed_sha_is_noop() -> None:
    prev = PrState("sha1", _T0, "sha1")
    d = decide_pr(1, "sha1", prev, _T0 + timedelta(hours=2), _DB)
    assert d.dispatch is False


class _FakeGH:
    def __init__(self, prs: list[tuple[int, str]], ci_failed: bool = False) -> None:
        self._prs = prs
        self._ci_failed = ci_failed

    async def list_open_prs(self, repo: str):  # type: ignore[no-untyped-def]
        return Ok(self._prs)

    async def checks_failed(self, repo: str, sha: str):  # type: ignore[no-untyped-def]
        return Ok(self._ci_failed)


async def test_tick_dispatches_correct_after_debounce() -> None:
    store = InMemoryStore()
    gh = _FakeGH([(7, "shaX", "alice")])
    # 1ª passada: só registra o PR, nada enfileirado (espera estabilizar)
    await process_pr_poll_tick(
        gh, store, tenant="acme", repos=["acme/app"], now=lambda: _T0, debounce_seconds=1800
    )
    assert await store.list_runs("acme", 10) == []
    # 2ª passada 31 min depois, MESMO sha: estabilizou -> enfileira um `correct`
    later = _T0 + timedelta(minutes=31)
    await process_pr_poll_tick(
        gh, store, tenant="acme", repos=["acme/app"], now=lambda: later, debounce_seconds=1800
    )
    runs = await store.list_runs("acme", 10)
    assert len(runs) == 1
    assert runs[0].agent == "correct"
    assert runs[0].issue_id == "7"


def test_is_bot_author() -> None:
    from roboto.app.pr_poll import is_bot_author

    assert is_bot_author("renovate[bot]")
    assert is_bot_author("dependabot[bot]")
    assert is_bot_author("github-actions[bot]")
    assert not is_bot_author("alice")
    assert not is_bot_author("XimitGaia")


async def test_tick_skips_bot_prs() -> None:
    # polling PULA PRs de bot (renovate/dependabot) — não gasta token revisando PR de dependência
    store = InMemoryStore()
    gh = _FakeGH([(9, "shaB", "renovate[bot]")])
    later = _T0 + timedelta(minutes=31)
    for t in (_T0, later):  # mesmo estabilizando, nunca enfileira
        await process_pr_poll_tick(
            gh, store, tenant="acme", repos=["acme/app"], now=lambda t=t: t, debounce_seconds=1800
        )
    assert await store.list_runs("acme", 10) == []  # nenhum run p/ PR de bot


async def test_tick_ci_failed_dispatches_before_debounce() -> None:
    # check_suite falhou -> antecipa o `correct` sem esperar o debounce de 30 min (#166).
    store = InMemoryStore()
    gh = _FakeGH([(7, "shaX", "alice")], ci_failed=True)
    # 1ª passada: registra o PR (ainda não avalia)
    await process_pr_poll_tick(
        gh, store, tenant="acme", repos=["acme/app"], now=lambda: _T0, debounce_seconds=1800
    )
    assert await store.list_runs("acme", 10) == []
    # 2ª passada 1 min depois (DENTRO do debounce), mas CI falhou -> dispara já
    later = _T0 + timedelta(minutes=1)
    await process_pr_poll_tick(
        gh, store, tenant="acme", repos=["acme/app"], now=lambda: later, debounce_seconds=1800
    )
    runs = await store.list_runs("acme", 10)
    assert len(runs) == 1 and runs[0].agent == "correct"
