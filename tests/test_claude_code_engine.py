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


def test_accepts_disallowed_tools_for_least_privilege() -> None:
    engine = ClaudeCodeEngine(disallowed_tools=["Write", "Edit", "Bash"])
    assert engine._disallowed_tools == ["Write", "Edit", "Bash"]


def test_disallowed_tools_default_empty() -> None:
    assert ClaudeCodeEngine()._disallowed_tools == []


# --- resume-on-max_turns (#232) -----------------------------------------------------------------
import sys  # noqa: E402
import types  # noqa: E402

import pytest  # noqa: E402

from roboto.engines.claude_code import _is_max_turns  # noqa: E402
from roboto.engines.port import EngineEventKind  # noqa: E402


def test_is_max_turns() -> None:
    assert _is_max_turns("error_max_turns", "")
    assert _is_max_turns("error", "Reached maximum number of turns (80)")
    assert not _is_max_turns("error", "some other error")
    assert not _is_max_turns("success", "")


class _Text:
    def __init__(self, text: str) -> None:
        self.text = text


class AssistantMessage:  # nome EXATO: o engine faz type(m).__name__ == "AssistantMessage"
    def __init__(self, content: list[object]) -> None:
        self.content = content


class ResultMessage:
    def __init__(self, session_id: str, subtype: str, result: str = "", usage: dict | None = None):
        self.session_id = session_id
        self.subtype = subtype
        self.result = result
        self.usage = usage or {}


def _fake_sdk(segments: list[list[object]]) -> types.ModuleType:
    """SDK fake: cada chamada de query() emite o próximo 'segmento' de mensagens (simula resume)."""
    mod = types.ModuleType("claude_agent_sdk")
    calls: list[dict] = []

    class ClaudeAgentOptions:
        def __init__(self, **kw: object) -> None:
            self.kw = kw

    async def query(prompt: str, options: object):  # noqa: ANN202
        i = len(calls)
        calls.append({"prompt": prompt, "resume": options.kw.get("resume")})  # type: ignore[attr-defined]
        for m in segments[min(i, len(segments) - 1)]:
            yield m

    mod.ClaudeAgentOptions = ClaudeAgentOptions  # type: ignore[attr-defined]
    mod.query = query  # type: ignore[attr-defined]
    mod._calls = calls  # type: ignore[attr-defined]
    return mod


async def test_resume_on_max_turns_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    seg1 = [
        AssistantMessage([_Text("trabalhando")]),
        ResultMessage("s1", "error_max_turns", "Reached maximum number of turns (80)",
                      {"input_tokens": 100, "output_tokens": 10}),
    ]
    seg2 = [ResultMessage("s1", "success", "", {"input_tokens": 50, "output_tokens": 5})]
    fake = _fake_sdk([seg1, seg2])
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    eng = ClaudeCodeEngine(max_turns=80, max_resumes=1)
    await eng.start(_spec())
    kinds = [e.kind async for e in eng.events()]
    assert EngineEventKind.FAILED not in kinds  # não falhou — resumiu
    assert EngineEventKind.FINISHED in kinds  # concluiu no 2º segmento
    assert len(fake._calls) == 2  # type: ignore[attr-defined]
    assert fake._calls[1]["resume"] == "s1"  # type: ignore[attr-defined]  # resumiu a sessão


async def test_max_turns_without_resume_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    seg = [ResultMessage("s1", "error_max_turns", "Reached maximum number of turns (80)")]
    fake = _fake_sdk([seg])
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    eng = ClaudeCodeEngine(max_turns=80, max_resumes=0)
    await eng.start(_spec())
    kinds = [e.kind async for e in eng.events()]
    assert EngineEventKind.FAILED in kinds  # sem resume → falha (comportamento antigo)
    assert len(fake._calls) == 1  # type: ignore[attr-defined]
