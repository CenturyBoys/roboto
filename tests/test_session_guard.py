"""Testes do guard de sessão (#266, app.session_guard)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.session_guard import may_resume, resumable_native_id, session_config_hash
from roboto.orchestrator.model import Engine, Session


def _session(sid: int, native: str | None, config_hash: str | None) -> Session:
    now = datetime(2026, 11, 18, tzinfo=UTC)
    return Session(
        id=sid,
        tenant="t1",
        execution_id=1,
        engine=Engine.CLAUDE_CODE,
        state="active",
        created_at=now,
        updated_at=now,
        native_session_id=native,
        config_hash=config_hash,
    )


def test_hash_stable_and_order_independent() -> None:
    a = session_config_hash(model="qwen", tools=("Read", "Bash"))
    b = session_config_hash(model="qwen", tools=("Bash", "Read"))
    assert a == b  # a ordem das tools não muda a config


def test_hash_changes_with_model_or_tools_or_extra() -> None:
    base = session_config_hash(model="qwen", tools=("Read",))
    assert base != session_config_hash(model="deepseek", tools=("Read",))
    assert base != session_config_hash(model="qwen", tools=("Read", "Bash"))
    assert base != session_config_hash(model="qwen", tools=("Read",), extra="system-v2")


def test_may_resume_only_on_equal_hash() -> None:
    h = session_config_hash(model="qwen")
    assert may_resume(h, h)
    assert not may_resume(None, h)  # sem hash guardado → não retoma
    assert not may_resume("outro", h)


def test_resumable_picks_latest_matching() -> None:
    h = session_config_hash(model="qwen")
    other = session_config_hash(model="deepseek")
    sessions = [
        _session(1, "nat-1", h),
        _session(2, "nat-2", other),  # config diferente: ignorada
        _session(3, "nat-3", h),  # mais recente compatível
    ]
    assert resumable_native_id(sessions, h) == "nat-3"


def test_resumable_none_when_no_match() -> None:
    h = session_config_hash(model="qwen")
    sessions = [
        _session(1, "nat-1", session_config_hash(model="deepseek")),
        _session(2, None, h),  # compatível mas sem id nativo: inútil pra resume
    ]
    assert resumable_native_id(sessions, h) is None
