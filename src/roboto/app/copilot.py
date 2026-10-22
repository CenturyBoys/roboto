"""Driver de sessão INTERATIVA (co-piloto, trilha O Fatia 5) sobre o `ClaudeSDKClient`.

⚠️ **PoC — valida no ambiente com modelo (N2/N3).** Diferente do ciclo batch (`run_pr_cycle`, que
usa `query()` one-shot), aqui a sessão fica **viva**: o humano manda mensagens no meio (steer),
aprova/nega ferramentas e interrompe — tudo pelo cockpit, via `SessionHub`. NÃO é plugado no loop
default do `runtime` (precisa de motor+modelo reais e de PoC vivo antes); import do SDK é **lazy**
(não afeta o tier-1). A API segue a doc do Agent SDK (`ClaudeSDKClient`, `can_use_tool`).

Fluxo (per a pesquisa do SDK):
- `permission_mode="default"` + `can_use_tool` ⇒ cada ação que pede permissão vira uma
  **interação de aprovação** (D24); o callback **aguarda** o `Future` do hub até o humano decidir.
- após cada resposta (`receive_response` até o `ResultMessage`), o driver espera a próxima
  mensagem humana (`live.next_input()`) e reenvia com `client.query(...)` — mantém o contexto.
- `live.interrupt_requested` ⇒ `client.interrupt()`.
- mensagens/tool-calls viram `session_event` (feed ao vivo, Fatia 2); mapeia o `session_id` nativo.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from roboto.app.human import request_human_input
from roboto.app.session_hub import SessionHub
from roboto.orchestrator.model import Engine, InteractionKind, Run
from roboto.orchestrator.store import Store


async def drive_session(
    store: Store,
    hub: SessionHub,
    *,
    run: Run,
    chat_id: str,
    workdir: str,
    now: Callable[[], datetime],
    model: str = "",
    mcp_servers: dict[str, object] | None = None,
) -> None:
    # lazy: só o PoC do co-piloto precisa do SDK (tier-1 não importa isto)
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

    live = hub.open(run.id)

    async def can_use_tool(
        tool_name: str, input_data: dict[str, object], context: object
    ) -> object:
        # vira aprovação humana (D24) e ESPERA a decisão (console/Telegram resolve o Future do hub)
        summary = str(input_data.get("command") or input_data.get("file_path") or "")
        created = await request_human_input(
            store,
            tenant=run.tenant,
            execution_id=run.id,
            chat_id=chat_id,
            kind=InteractionKind.APPROVAL,
            prompt=f"Aprovar {tool_name}? {summary}".strip(),
            options=["aprovar", "negar"],
            now=now(),
        )
        if not hasattr(created, "value"):  # falha ao registrar -> nega por segurança (H)
            return PermissionResultDeny(message="não consegui registrar a aprovação")
        approved = await live.request_approval(created.value.id)
        if approved:
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(message="humano negou no cockpit")

    async def _keep_stream_open(
        input_data: object, tool_use_id: object, context: object
    ) -> dict[str, object]:
        return {}  # workaround (SDK >=0.2.140): hook PreToolUse mantém o stream p/ o can_use_tool

    options = ClaudeAgentOptions(
        cwd=workdir,
        permission_mode="default",  # é o que faz o can_use_tool ser chamado (não bypass)
        can_use_tool=can_use_tool,
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_keep_stream_open])]},
        model=model or None,
        mcp_servers=mcp_servers,
    )

    prompt = f"Trabalhe a issue {run.issue_id} do repo {run.repo} (cwd {workdir})."
    try:
        async with ClaudeSDKClient(options=options) as client:
            while True:
                await client.query(prompt)
                async for message in client.receive_response():
                    if live.interrupt_requested:
                        await client.interrupt()
                    name = type(message).__name__
                    if name == "AssistantMessage":
                        for block in getattr(message, "content", []) or []:
                            if hasattr(block, "text"):
                                await store.append_session_event(
                                    run.tenant, run.id, "message", now(), text=str(block.text)
                                )
                            elif hasattr(block, "name"):  # tool_use
                                await store.append_session_event(
                                    run.tenant, run.id, "tool_call", now(), tool=str(block.name)
                                )
                    elif name == "ResultMessage":
                        native = str(getattr(message, "session_id", "") or "")
                        if native:  # mapeia sessão nativa -> interna (D23); habilita resume
                            session = await store.create_session(
                                run.tenant, run.id, Engine.CLAUDE_CODE, now()
                            )
                            await store.set_native_session(session.id, native, now())
                # turno concluído: espera a próxima mensagem humana (steer) e segue a MESMA sessão
                prompt = await live.next_input()
    finally:
        hub.close(run.id)
