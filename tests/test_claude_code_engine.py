"""ClaudeCodeEngine — partes sem SDK (import lazy; events() precisa do SDK e não roda no CI)."""

from __future__ import annotations

from roboto.engines.claude_code import ClaudeCodeEngine
from roboto.engines.port import RunSpec
from roboto.orchestrator.model import Engine
from roboto.result import Ok


def _spec(resume: str | None = None) -> RunSpec:
    return RunSpec(
        tenant="acme", repo="acme/app", workdir="/work", prompt="faça X", resume_session_id=resume
    )


def test_engine_identity() -> None:
    assert ClaudeCodeEngine().engine is Engine.CLAUDE_CODE


async def test_start_returns_resume_id_without_sdk() -> None:
    engine = ClaudeCodeEngine()
    started = await engine.start(_spec(resume="sess-1"))
    assert isinstance(started, Ok)
    assert started.value == "sess-1"
    assert engine.session_id == "sess-1"


async def test_start_fresh_has_empty_session() -> None:
    engine = ClaudeCodeEngine()
    started = await engine.start(_spec())
    assert isinstance(started, Ok)
    assert started.value == ""


async def test_respond_and_interrupt_are_ok() -> None:
    engine = ClaudeCodeEngine()
    assert isinstance(await engine.respond("2"), Ok)
    assert isinstance(await engine.interrupt(), Ok)


def test_accepts_mcp_servers_for_code_intel() -> None:
    mcp = {"code-intel": {"command": "code-intel-mcp"}}
    engine = ClaudeCodeEngine(mcp_servers=mcp)  # type: ignore[arg-type]
    assert engine._mcp_servers == mcp
