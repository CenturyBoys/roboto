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


def _is_max_turns(subtype: str, result: str) -> bool:
    """O ResultMessage de erro é 'bateu o max_turns'? (p/ decidir resume vs FAILED, #232). Pura."""
    s = (subtype or "").lower()
    r = (result or "").lower()
    return "max_turn" in s or "maximum number of turns" in r or "maximum turns" in r


def _over_token_budget(tokens_in: int, tokens_out: int, budget: int) -> bool:
    """Estourou o budget de tokens do run? (#242 Fatia 2) — budget<=0 desliga. Pura/testável."""
    return budget > 0 and (tokens_in + tokens_out) > budget


class ClaudeCodeEngine:
    def __init__(
        self,
        *,
        model: str = "",
        # acceptEdits: libera edição de arquivo sem a flag bloqueada como root (PoC validou).
        # Autonomia total (git/pnpm/PR) exige bypassPermissions -> rodar o container NÃO-root.
        permission_mode: str = "acceptEdits",
        allowed_tools: list[str] | None = None,
        # least privilege por task (H): ferramentas NEGADAS (ex.: mutação p/ agente read-only).
        disallowed_tools: list[str] | None = None,
        mcp_servers: dict[str, object] | None = None,  # ex.: code-intel (ide_cc) — F, menos token
        max_turns: int = 0,  # teto de turnos (0 = sem teto); backstop contra sprawl/runaway (token)
        # resume-on-max_turns (#232): ao bater o max_turns, RESUME a sessão (continua de onde parou,
        # WIP salvo no /work) em vez de FAILED. 0 = sem resume (comportamento antigo).
        max_resumes: int = 0,
        # thinking budget: liga o reasoning (ccr mapeia thinking→reasoning). NECESSÁRIO p/ modelos
        # reasoning-mandatory via OpenRouter (ex.: gpt-oss — senão 400 "cannot be disabled").
        max_thinking_tokens: int = 0,
        # budget de tokens por run (#242 Fatia 2): estourou → NÃO resume e termina (provável
        # flailing). Corta a multiplicação do burn (exec #80: 194k). 0 = sem budget.
        token_budget: int = 0,
        # buffer do stdout do SDK (default 1MB mata run verboso, #70/#83). 0 = default do SDK.
        max_buffer_size: int = 0,
        # cap de tool-calls por run (#242): modelo fraco flaila (exec #96: 172 tools, 3.4M tokens).
        # O budget de token só checa no fim do segmento — o cap de tools corta MID-STREAM. 0 = sem.
        max_tools: int = 0,
    ) -> None:
        self._model = model
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools or []
        self._disallowed_tools = disallowed_tools or []
        self._mcp_servers = mcp_servers
        self._max_turns = max_turns
        self._max_resumes = max_resumes
        self._max_thinking_tokens = max_thinking_tokens
        self._token_budget = token_budget
        self._max_buffer_size = max_buffer_size
        self._max_tools = max_tools
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

        resume_id = self._spec.resume_session_id or None
        prompt = self._spec.prompt
        resumes_left = self._max_resumes
        tin_acc = tout_acc = 0  # tokens acumulam entre os segmentos (resume)
        tool_count = 0  # cap de flailing (#242/#96): total de tool-calls do run; corta MID-STREAM
        while True:
            options = ClaudeAgentOptions(
                cwd=self._spec.workdir,
                permission_mode=self._permission_mode,
                allowed_tools=self._allowed_tools,
                disallowed_tools=self._disallowed_tools,  # least privilege por task (H)
                resume=resume_id,
                # modelo por-run (spec.model) tem precedência sobre o fixo do construtor: deixa o
                # right-sizing escolher o tier (forte/barato) por tarefa (ver app/tiering.py).
                model=(self._spec.model or self._model) or None,
                mcp_servers=self._mcp_servers,  # code-intel (navegação semântica, F)
                max_turns=self._max_turns or None,
                max_thinking_tokens=self._max_thinking_tokens or None,  # liga reasoning (gpt-oss)
                # buffer do stdout NDJSON do SDK (default 1MB). Modelo verboso (qwen-80b) emite uma
                # mensagem única >1MB → "JSON message exceeded buffer" MATAVA o run (#70/#83). Sobe.
                max_buffer_size=self._max_buffer_size or None,
            )
            hit_max = False
            async for message in query(prompt=prompt, options=options):
                name = type(message).__name__
                if name == "AssistantMessage":
                    for block in getattr(message, "content", []) or []:
                        if hasattr(block, "text"):
                            yield EngineEvent(EngineEventKind.MESSAGE, text=str(block.text))
                        elif hasattr(block, "name"):  # tool_use
                            yield EngineEvent(EngineEventKind.TOOL_CALL, tool=str(block.name))
                            tool_count += 1
                            # cap de flailing (#96): modelo fraco loopa (172 tools, 3.4M tokens). O
                            # budget de token só vê no fim do segmento — o cap de tool corta AGORA.
                            if self._max_tools and tool_count > self._max_tools:
                                yield EngineEvent(
                                    EngineEventKind.FAILED,
                                    text=f"flailing: {tool_count} tool-calls (> {self._max_tools}) "
                                    "— abortado p/ não queimar token (provável loop)",
                                )
                                return
                elif name == "ResultMessage":
                    self._session_id = str(getattr(message, "session_id", "") or "")
                    usage = getattr(message, "usage", {}) or {}
                    tin_acc += int(usage.get("input_tokens", 0) or 0)
                    tout_acc += int(usage.get("output_tokens", 0) or 0)
                    subtype = str(getattr(message, "subtype", "success"))
                    result_text = str(getattr(message, "result", "") or "")
                    over_budget = _over_token_budget(tin_acc, tout_acc, self._token_budget)
                    can_resume = (
                        resumes_left > 0
                        and bool(self._session_id)
                        and _is_max_turns(subtype, result_text)
                        and not over_budget  # #242: estourou o budget → NÃO resume (corta o burn)
                    )
                    if subtype == "success":
                        yield EngineEvent(
                            EngineEventKind.FINISHED, tokens_in=tin_acc, tokens_out=tout_acc
                        )
                    elif over_budget:
                        gasto = (tin_acc + tout_acc) // 1000
                        yield EngineEvent(
                            EngineEventKind.FAILED,
                            text=f"budget de tokens estourado ({gasto}k) — provável flailing",
                        )
                    elif can_resume:
                        hit_max = True  # RESUME (#232): não falha; WIP salvo no /work
                    else:
                        yield EngineEvent(EngineEventKind.FAILED, text=result_text or subtype)
            if hit_max:
                resumes_left -= 1
                resume_id = self._session_id
                prompt = (
                    "Você bateu o limite de turnos ANTES de concluir, mas seu trabalho JÁ ESTÁ "
                    "salvo no repo. CONTINUE de onde parou: NÃO recomece nem re-explore — finalize "
                    "só o que falta (ajuste final + self-check rápido do que mudou) e termine."
                )
                continue
            break
        # TODO(PoC): aprovação por ação (can_use_tool -> NEEDS_APPROVAL) e interrupção real
        # (ClaudeSDKClient.interrupt; query() não cancela). Ver N2/N3.

    async def respond(self, answer: str) -> Result[None, Error]:
        # retomada = novo start(resume_session_id) com a resposta no prompt (N2)
        return Ok(None)

    async def interrupt(self) -> Result[None, Error]:
        return Ok(None)  # TODO(PoC): usar ClaudeSDKClient p/ cancelamento real
