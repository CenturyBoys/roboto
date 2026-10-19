"""Matriz de capacidades por motor (D22) — resultado do levantamento (out/2026).

Cristaliza o PoC de pesquisa: o que cada motor faz **nativo**, o que o **host** supre, o que é
**parcial** (exige confirmação em PoC real) e o que **não** há. O registro de motores (D22) usa
isto para degradar graciosamente por motor/versão. Fontes nos docs oficiais de cada motor.

`level`: native | host | partial | none.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from roboto.orchestrator.model import Engine


class Capability(StrEnum):
    START_HEADLESS = "start_headless"
    STREAM_EVENTS = "stream_events"
    APPROVE_PER_ACTION = "approve_per_action"
    REQUEST_HUMAN_INPUT = "request_human_input"
    RESUME_SESSION = "resume_session"
    INTERRUPT = "interrupt"
    STRUCTURED_RESULT = "structured_result"


@dataclass(frozen=True)
class CapabilitySupport:
    level: str
    mechanism: str
    caveat: str = ""


# Claude Code (Agent SDK Python + CLI). Fonte: code.claude.com/docs/en/agent-sdk/*
CLAUDE_CODE_CAPS: dict[Capability, CapabilitySupport] = {
    Capability.START_HEADLESS: CapabilitySupport(
        "native", "query()/ClaudeSDKClient; ANTHROPIC_API_KEY no env", "sessão nova por chamada"
    ),
    Capability.STREAM_EVENTS: CapabilitySupport(
        "native", "include_partial_messages -> StreamEvent/AssistantMessage",
        "deltas de token agregados só no ResultMessage.usage"
    ),
    Capability.APPROVE_PER_ACTION: CapabilitySupport(
        "native", "callback can_use_tool -> PermissionResultAllow/Deny",
        "NÃO dispara para tools pré-aprovadas (allowed_tools/permission_mode)"
    ),
    Capability.REQUEST_HUMAN_INPUT: CapabilitySupport(
        "partial", "AskUserQuestion (model-triggered) OU deny(interrupt)+re-query",
        "sem pause nativa; retomada é manual pelo host — validar ergonomia em PoC"
    ),
    Capability.RESUME_SESSION: CapabilitySupport(
        "native", "ResultMessage.session_id (UUID) + options.resume=id",
        "transcript JSONL interno; extrair id do ResultMessage"
    ),
    Capability.INTERRUPT: CapabilitySupport(
        "native", "ClaudeSDKClient.interrupt()",
        "só em streaming (ClaudeSDKClient); query() single-shot não interrompe"
    ),
    Capability.STRUCTURED_RESULT: CapabilitySupport(
        "native", "ResultMessage.usage/total_cost_usd/structured_output", "cost pode ser None"
    ),
}

# Codex (SDK openai-codex / app-server JSON-RPC). Fonte: learn.chatgpt.com/docs/app-server + repo
CODEX_CAPS: dict[Capability, CapabilitySupport] = {
    Capability.START_HEADLESS: CapabilitySupport(
        "native", "AsyncCodex().thread_start()+turn(); OU codex app-server (JSON-RPC)",
        "codex exec --json é one-shot e NÃO intercepta aprovação"
    ),
    Capability.STREAM_EVENTS: CapabilitySupport(
        "native", "turn_handle.stream() / notifications item/* do app-server",
        "schema do exec --json é instável/não-versionado; usar SDK/app-server"
    ),
    Capability.APPROVE_PER_ACTION: CapabilitySupport(
        "partial", "app-server item/permissions/requestApproval (server->client)",
        "SDK de alto nível só tem ApprovalMode grosso (auto/deny) — PoC: usar app-server cru"
    ),
    Capability.REQUEST_HUMAN_INPUT: CapabilitySupport(
        "partial", "app-server tool/requestUserInput + turn/steer (mid-turn)",
        "só no app-server/SDK, não no exec; pausar-entre-turnos = encerrar + thread/resume"
    ),
    Capability.RESUME_SESSION: CapabilitySupport(
        "native", "threadId + thread_resume(); JSONL em $CODEX_HOME",
        "sobrevive a restart; --ephemeral desativa persistência"
    ),
    Capability.INTERRUPT: CapabilitySupport(
        "native", "turn/interrupt / turn_handle.interrupt()",
        "usage de turno interrompido pode não ser reportado (issue #50586)"
    ),
    Capability.STRUCTURED_RESULT: CapabilitySupport(
        "native", "TurnResult.final_response + thread.usage; --output-schema",
        "turn.failed pode vir sem usage"
    ),
}

CAPABILITIES: dict[Engine, dict[Capability, CapabilitySupport]] = {
    Engine.CLAUDE_CODE: CLAUDE_CODE_CAPS,
    Engine.CODEX: CODEX_CAPS,
}
