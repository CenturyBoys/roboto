"""Gatilho por comentário `@potter` (#166): lógica pura + tick, com anti-loop por marcador."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.comment_poll import (
    BOT_MARKER,
    CommentCmd,
    decide_comment_commands,
    process_comment_poll_tick,
)
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def test_decide_dispatches_command() -> None:
    comments = [(10, 216, "@potter implementa"), (11, 216, "só um comentário")]
    cmds, cur = decide_comment_commands(comments, 0)
    assert cmds == [CommentCmd(10, 216, "impl")]
    assert cur == 11


def test_decide_skips_bot_marker() -> None:
    cmds, cur = decide_comment_commands([(12, 7, f"@potter revisa\n{BOT_MARKER}")], 0)
    assert cmds == []  # é do próprio bot -> anti-loop
    assert cur == 12


def test_decide_skips_below_cursor() -> None:
    cmds, _ = decide_comment_commands([(5, 7, "@potter implementa")], 5)
    assert cmds == []  # já visto


def test_decide_unknown_command_ignored() -> None:
    cmds, _ = decide_comment_commands([(20, 7, "@potter dança")], 0)
    assert cmds == []


class _FakeGH:
    def __init__(self, comments: list[tuple[int, int, str]]) -> None:
        self._c = comments

    async def list_recent_comments(self, repo: str):  # type: ignore[no-untyped-def]
        return Ok(self._c)


async def test_tick_enqueues_and_advances_cursor() -> None:
    store = InMemoryStore()
    gh = _FakeGH([(10, 216, "@potter revisa")])
    await process_comment_poll_tick(gh, store, tenant="acme", repos=["acme/app"], now=lambda: _T0)
    runs = await store.list_runs("acme", 10)
    assert len(runs) == 1 and runs[0].agent == "correct" and runs[0].issue_id == "216"
    assert await store.get_channel_offset("acme", "ghc:acme/app") == 10
    # 2ª passada: cursor já avançou -> não re-dispara
    await process_comment_poll_tick(gh, store, tenant="acme", repos=["acme/app"], now=lambda: _T0)
    assert len(await store.list_runs("acme", 10)) == 1
