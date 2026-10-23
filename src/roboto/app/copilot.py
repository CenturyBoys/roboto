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

import asyncio
from collections.abc import Callable
from datetime import datetime

from roboto.app.session_hub import SessionHub
from roboto.orchestrator.model import Engine, Run
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
    initial_prompt: str | None = None,
) -> None:
    # lazy: só o PoC do co-piloto precisa do SDK (tier-1 não importa isto)
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    # Reutiliza a sessão que o starter já abriu (evita corrida: o console precisa
    # enxergar a LiveSession na PRÓXIMA mensagem, antes deste task rodar). Se
    # ninguém pré-abriu, abre aqui.
    live = hub.get(run.id) or hub.open(run.id)

    # co-piloto CONVERSACIONAL (não agente autônomo): responde direto, lê o mínimo, não varre o repo
    # sem o humano pedir. `max_turns` é o teto por mensagem (evita o motor "não parar").
    copilot_system = (
        "Você é um co-piloto conversacional dentro do cockpit, ajudando a discutir e refinar a "
        "issue em contexto. Responda de forma DIRETA e CONCISA. Leia o repositório só quando for "
        "necessário pra responder (Read/Grep pontuais) — NÃO faça varreduras longas nem trabalho "
        "autônomo extenso sem o humano pedir. Ao refinar: faça no máximo UMA pergunta por vez OU "
        "proponha um trecho curto, e pergunte antes de qualquer ação grande."
    )
    # Motor fixo do PoC: sem isto o CLI cai num default (ex.: um "claude-opus-*" inexistente no
    # roteamento via ccr/OpenRouter), que derrubava a sessão do chat com erro de modelo.
    model = model or "qwen/qwen3-coder"

    # RETOMA a última sessão nativa do run (o refino / a mensagem anterior do chat): o motor volta
    # COM o contexto já lido, então responde DIRETO em vez de revarrer o repo do zero a cada
    # mensagem — era isso que estourava o `max_turns` e deixava o chat "empacado" sem resposta.
    resume: str | None = None
    for s in await store.sessions_for_execution(run.id):
        if s.native_session_id:
            resume = s.native_session_id  # pega a mais recente (a lista vem em ordem)

    def _build_options(resume_id: str | None) -> ClaudeAgentOptions:
        # bypassPermissions: leitura FLUIDA (não trava pedindo aprovação a cada ação, o que deixava
        # o run em "awaiting" e impedia o interromper). O humano controla por interromper/encerrar.
        return ClaudeAgentOptions(
            cwd=workdir,
            permission_mode="bypassPermissions",
            system_prompt=copilot_system,
            # teto por mensagem: alto o bastante pra uma resposta real (ler pontual + responder) sem
            # empacar, mas ainda um backstop contra runaway. Com `resume`, raramente chega perto.
            max_turns=24,
            model=model or None,
            mcp_servers=mcp_servers,
            resume=resume_id,
        )

    # 1ª mensagem do humano (quando a sessão é aberta sob demanda pelo chat) semeia
    # o turno; sem ela, cai no prompt padrão de trabalhar a issue.
    prompt = initial_prompt or (
        f"Trabalhe a issue {run.issue_id} do repo {run.repo} (cwd {workdir})."
    )
    native_mapped = False
    try:
        # `resume` aponta pra uma conversa em DISCO do Claude Code; um rebuild/restart do container
        # apaga esses arquivos e deixa o id órfão ("No conversation found"), o que derrubava o chat
        # inteiro. Se o resume falhar, cai pra sessão NOVA em vez de morrer.
        client = ClaudeSDKClient(options=_build_options(resume))
        try:
            await client.connect()
        except Exception:  # noqa: BLE001 — resume órfão (rebuild) / falha de conexão
            if resume is None:
                raise
            client = ClaudeSDKClient(options=_build_options(None))
            await client.connect()

        # Vigia concorrente: corta o motor NO INSTANTE em que o humano pede interromper/encerrar
        # — fora do loop de stream (prioridade máxima; não espera a próxima mensagem chegar).
        async def _controls() -> None:
            while True:
                await live.wait_control()
                try:
                    await client.interrupt()
                except Exception:  # noqa: BLE001 — interrupt pode não ter nada rodando
                    pass
                if live.ended:
                    return
                live.clear_interrupt()  # interrupção tratada; segue vigiando

        watcher = asyncio.create_task(_controls())
        try:
            while True:
                await client.query(prompt)
                async for message in client.receive_response():
                    name = type(message).__name__
                    # mapeia a sessão nativa -> interna (D23) assim que o id aparece
                    native = str(getattr(message, "session_id", "") or "")
                    if native and not native_mapped:
                        session = await store.create_session(
                            run.tenant, run.id, Engine.CLAUDE_CODE, now()
                        )
                        await store.set_native_session(session.id, native, now())
                        native_mapped = True
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
                if live.ended:  # encerrar pedido durante o turno: sai já
                    break
                # turno concluído: espera a próxima mensagem (steer); None = encerrar
                nxt = await live.next_input()
                if nxt is None:
                    break
                prompt = nxt
        finally:
            watcher.cancel()
            await client.disconnect()
    finally:
        hub.close(run.id)
