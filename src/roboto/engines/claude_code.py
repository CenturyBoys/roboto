"""Adapter do Claude Code (Agent SDK) — motor de coding real (D22).

Backeado por **Qwen via claude-code-router** (`ANTHROPIC_BASE_URL`). **Primeiro corte**: mapeia o
stream do SDK para `EngineEvent`; start/resume por `session_id`. A **aprovação por ação** e a
**interrupção** dependem de detalhes do SDK (callback `can_use_tool` / `ClaudeSDKClient.interrupt`)
que só fecham no **PoC vivo** — marcados com TODO (ver `research/N2`/`N3`). Import do SDK é **lazy**
(não quebra o tier-1 quando o SDK não está instalado); dispatch por nome de tipo evita acoplar à
forma exata das classes do SDK.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from roboto.engines.port import EngineEvent, EngineEventKind, RunSpec
from roboto.orchestrator.model import Engine, Error
from roboto.result import Ok, Result


class ClaudeCodeEngine:
    def __init__(
        self,
        *,
        model: str = "",
        permission_mode: str = "default",
        allowed_tools: list[str] | None = None,
    ) -> None:
        self._model = model
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools or []
        self._spec: RunSpec | None = None
        self._session_id = ""

    @property
    def engine(self) -> Engine:
        return Engine.CLAUDE_CODE

    @property
    def session_id(self) -> str:
        return self._session_id

    async def start(self, spec: RunSpec) -> Result[str, Error]:
        self._spec = spec
        self._session_id = spec.resume_session_id or ""
        return Ok(self._session_id)  # id real chega no ResultMessage durante events()

    async def events(self) -> AsyncIterator[EngineEvent]:
        if self._spec is None:
            return
        from claude_agent_sdk import ClaudeAgentOptions, query  # lazy; validar versão no PoC

        options = ClaudeAgentOptions(
            cwd=self._spec.workdir,
            permission_mode=self._permission_mode,
            allowed_tools=self._allowed_tools,
            resume=self._spec.resume_session_id or None,
            model=self._model or None,
        )
        async for message in query(prompt=self._spec.prompt, options=options):
            name = type(message).__name__
            if name == "AssistantMessage":
                for block in getattr(message, "content", []) or []:
                    if hasattr(block, "text"):
                        yield EngineEvent(EngineEventKind.MESSAGE, text=str(block.text))
                    elif hasattr(block, "name"):  # tool_use
                        yield EngineEvent(EngineEventKind.TOOL_CALL, tool=str(block.name))
            elif name == "ResultMessage":
                self._session_id = str(getattr(message, "session_id", "") or "")
                usage = getattr(message, "usage", {}) or {}
                if getattr(message, "is_error", False):
                    yield EngineEvent(
                        EngineEventKind.FAILED, text=str(getattr(message, "result", "erro"))
                    )
                else:
                    yield EngineEvent(
                        EngineEventKind.FINISHED,
                        tokens_in=int(usage.get("input_tokens", 0) or 0),
                        tokens_out=int(usage.get("output_tokens", 0) or 0),
                    )
        # TODO(PoC): aprovação por ação (can_use_tool -> NEEDS_APPROVAL) e interrupção real
        # (ClaudeSDKClient.interrupt; query() não cancela). Ver N2/N3.

    async def respond(self, answer: str) -> Result[None, Error]:
        # retomada = novo start(resume_session_id) com a resposta no prompt (N2)
        return Ok(None)

    async def interrupt(self) -> Result[None, Error]:
        return Ok(None)  # TODO(PoC): usar ClaudeSDKClient p/ cancelamento real
