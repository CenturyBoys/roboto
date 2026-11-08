"""Entrypoint do daemon (D3): liga config -> store -> adapters -> servidor ASGI + laços.

Config vive no **banco** (fonte única, trilha O). O boot **semeia** o `.env` no banco (origem env
vira registro) e lê a config efetiva de lá. Se faltar algo obrigatório, sobe em **modo setup**
(cockpit + tela de config) em vez de morrer; quando a config fica completa, recarrega e sobe os
laços. `DATABASE_URL`/`CONSOLE_TOKEN` são bootstrap: só via env.

Glue fino (não coberto por tier-1: exige Postgres + uvicorn + credenciais). A lógica de cada peça é
testada isoladamente. Rode com `python -m roboto`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from roboto.app.compose import build_adapters
from roboto.app.loops import poll_tick, process_refine_tick, process_run_tick, run_periodic
from roboto.app.mcp_config import build_mcp_servers
from roboto.app.session_hub import SessionHub
from roboto.config import BOOTSTRAP_KEYS, Config, load_config, settable_from_env
from roboto.engines.stub import StubEngine
from roboto.llm.decide import Decider
from roboto.orchestrator.core import publish_outbox, sweep
from roboto.orchestrator.model import Run, RunState
from roboto.orchestrator.pg_store import PostgresStore
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok
from roboto.web.app import build_app
from roboto.web.setup import build_setup_app

_PORT = 8080

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


async def _run_daemon(config: Config, store: Store) -> None:
    adapters = build_adapters(config, store)  # router inclui telegram_question
    hub = SessionHub()  # sessões vivas do co-piloto (Fatia 5); o driver interativo as registra

    async def start_live_session(run: Run, initial_prompt: str) -> bool:
        """Abre uma sessão viva/steerable sob demanda para `run`, ligando o driver
        interativo (`drive_session`/`ClaudeSDKClient`) como task de fundo — é o que
        faz o chat do cockpit "conversar com a sessão viva". Idempotente; recusa se
        o motor não for o claude_code ou se o run estiver em RUNNING (tocado pelo
        ciclo automático), p/ não rodar dois motores no mesmo /work/{repo}."""
        if config.engine != "claude_code":
            return False
        if hub.get(run.id) is not None:
            return True  # já viva
        if run.state is RunState.RUNNING:
            return False  # ocupado pelo ciclo batch
        use_tmux = config.copilot_mode == "tmux"
        hub.open(run.id)  # abre já: a próxima mensagem do chat acha a LiveSession (sem corrida)
        # refino é read-only (lê p/ fundamentar, não implementa) — vale nos dois drivers
        read_only = run.agent == "refine"
        # busca web (Tavily) só no refino (H): fundamentar a issue com fontes externas (#203)
        mcp: dict[str, object] | None = build_mcp_servers(
            code_intel=config.code_intel, tavily_key=config.tavily_api_key, web=read_only
        )

        # injeta o contexto da issue (repo + #N + corpo) ANTES da mensagem do humano — senão o
        # motor não sabe de qual issue a conversa trata, mesmo o chat tendo sido aberto nela.
        prompt = initial_prompt
        if run.issue_id.isdigit():
            got = await adapters.github.get_issue(run.repo, int(run.issue_id))
            if isinstance(got, Ok):
                title, body = got.value
                prompt = (
                    f"Contexto: estamos trabalhando a issue #{run.issue_id} do repo {run.repo} "
                    f"(cwd {f'/work/{run.repo}'}).\nTítulo: {title}\nCorpo atual:\n{body}\n\n"
                    f"Mensagem do humano: {initial_prompt}"
                )

        async def _drive() -> None:
            try:
                if use_tmux:
                    from roboto.app.tmux_copilot import drive_session_tmux

                    await drive_session_tmux(
                        store, hub, run=run, chat_id=config.chat_id,
                        workdir=f"/work/{run.repo}", now=_now,
                        read_only=read_only, code_intel=config.code_intel,
                        initial_prompt=prompt,
                    )
                else:
                    from roboto.app.copilot import drive_session

                    await drive_session(
                        store, hub, run=run, chat_id=config.chat_id,
                        workdir=f"/work/{run.repo}", now=_now,
                        mcp_servers=mcp, initial_prompt=prompt,
                    )
            except Exception:  # noqa: BLE001 — task de fundo: loga e encerra limpo
                logger.exception("co-piloto: sessão viva run=%s terminou com erro", run.id)
            finally:
                hub.close(run.id)

        asyncio.create_task(_drive())
        return True

    app = build_app(
        store, config=config, hub=hub, issue_source=adapters.github,
        gateway=adapters.gateway, start_session=start_live_session,
    )
    stop = asyncio.Event()

    async def _poll() -> None:
        await poll_tick(
            adapters.channel,
            store,
            repo=config.default_repo,
            gateway=adapters.gateway,
            transcriber=adapters.transcriber,
            now=_now,
            github=adapters.github,  # habilita o comando "issues" (listar) no Telegram
            tenant=config.tenant,  # persiste o cursor do Telegram (não relê no restart)
            engine_scope=(config.engine == "claude_code"),
        )

    # preflight (K): valida pré-condições de infra antes de trabalhar — loga claro se faltar algo.
    import shutil

    from roboto.app.preflight import check as preflight_check

    _free_mb = shutil.disk_usage("/").free // (1024 * 1024)
    _pf = preflight_check(
        env=os.environ,
        required_keys=("OPENROUTER_API_KEY",),
        workdir=f"/work/{config.default_repo}",
        min_disk_mb=500,
        disk_free_mb=_free_mb,
    )
    for _c in _pf.checks:
        print(f"[preflight] {'✓' if _c.ok else '✗'} {_c.name}: {_c.detail}")
    if not _pf.ok:
        print(f"[preflight] ⚠️ {len(_pf.failures)} pré-condição(ões) falhou(ram) — pode flailar.")

    import uvicorn  # import tardio: só o daemon precisa

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=_PORT, log_level="info"))
    tasks = [
        server.serve(),
        run_periodic(_poll, 2.0, stop),
        run_periodic(lambda: publish_outbox(store, adapters.router, _now()), 1.0, stop),
        run_periodic(lambda: sweep(store, _now(), held=hub.live_ids()), 30.0, stop),
    ]

    # laço do motor de coding (D22/PoC N3), ligado por ROBOTO_ENGINE
    if config.engine == "stub":
        stub = StubEngine([])

        async def _run_stub() -> None:
            await process_run_tick(
                stub, store, tenant=config.tenant, chat_id=config.chat_id, now=_now
            )

        tasks.append(run_periodic(_run_stub, 5.0, stop))
    elif config.engine == "claude_code":
        from roboto.app.git_ops import SubprocessGit
        from roboto.app.pr_cycle import process_correct_tick, process_pr_run_tick
        from roboto.app.scope import process_scope_tick
        from roboto.engines.claude_code import ClaudeCodeEngine

        # imagem roda NÃO-root -> bypassPermissions (full-auto: git/pnpm/abrir PR).
        # code-intel (ide_cc) ligado por config -> navegação semântica, menos token (F).
        # impl NÃO recebe busca web (least-privilege, H) — só o refiner (abaixo).
        mcp: dict[str, object] | None = build_mcp_servers(code_intel=config.code_intel)
        # Modelo FIXO (ccr→OpenRouter/Qwen): sem isto o CLI cai no default (claude-opus-*), que o
        # ccr não roteia → a query falha com "selected model ... may not exist". O co-piloto já
        # fixava; o batch (impl/refino) precisa do mesmo pino.
        # DEVE bater com um id do poc/ccr.config.json (senão ccr responde unrecognized_model e o
        # run trava em running). Env p/ não voltar a driftar quando o ccr mudar o id.
        engine_model = os.environ.get("ROBOTO_ENGINE_MODEL", "qwen/qwen3-coder-next")
        # max_turns=80: implementação é mais longa que o refino (editar + rodar checks + corrigir),
        # mas ainda um backstop contra flail infinito (ex.: loop tentando instalar deps).
        claude = ClaudeCodeEngine(
            model=engine_model, permission_mode="bypassPermissions", mcp_servers=mcp,
            max_turns=120,  # folga p/ motor verborrágico (devstral explora muito); #232
            max_resumes=2,  # ao bater o teto, RESUME e conclui (WIP no /work) em vez de FAILED
            # liga reasoning p/ modelos reasoning-mandatory via ccr (gpt-oss); 0 = desligado
            max_thinking_tokens=int(os.environ.get("ROBOTO_THINKING_TOKENS", "0") or "0"),
            # budget de tokens (#242 Fatia 2): estourou → não resume e termina (corta o burn de
            # flailing, ex.: exec #80 = 194k). 0 = desligado. ROBOTO_TURN_TOKEN_BUDGET.
            token_budget=int(os.environ.get("ROBOTO_TURN_TOKEN_BUDGET", "0") or "0"),
        )
        # motor dedicado ao refino (read-only por prompt): evita corrida com o ciclo de PR.
        # max_turns=60: refino é LER+PROPOR; o PROMPT força parar em ~10 consultas, mas issues de
        # "discovery" puxam o modelo a explorar — teto um pouco maior como rede, e o prompt obriga
        # a terminar com a proposta (senão batia no teto em 0 mensagens e falhava).
        # least privilege (H): o refino é read-only (LÊ e PROPÕE a issue) — negar mutação/shell
        # fecha a brecha por política determinística, não só pelo prompt "read-only por prompt".
        from roboto.app.tool_policy import disallowed_tools_for

        # refiner: só code-intel. A busca web é HARNESS-DRIVEN (pre-step no process_refine_tick
        # roda o Tavily e injeta as fontes no prompt) — modelo local não invoca MCP de forma
        # confiável (#203, teste 2026-11-04: GLM travou no ToolSearch).
        refine_mcp = build_mcp_servers(code_intel=config.code_intel)
        refiner_engine = ClaudeCodeEngine(
            model=config.refine_model or engine_model,  # REFINE_MODEL: raciocínio forte no refino
            permission_mode="bypassPermissions",
            disallowed_tools=disallowed_tools_for("refine"),
            mcp_servers=refine_mcp,
            max_turns=60,
        )
        # Jev (degrau-2): decide a CRITICIDADE da pesquisa web no refino (trilha I/#222). Vazio =
        # sem Jev → o gate cai no keyword determinístico (degrau-1). Isolado atrás da porta Decider.
        refine_decider: Decider | None = None
        if config.jev_model:
            from roboto.llm.jev import JevDecider

            refine_decider = JevDecider(
                api_key=config.models.openrouter_api_key, model=config.jev_model
            )

        # second brain (G/D32): grava o PERFIL do repo (como operar) no boot — o motor não começa
        # cru. Determinístico (lê package.json/workspace); o prompt de impl injeta direto. kind
        # "perfil" + unique_by_ref: é DERIVADO do código (cache regenerável), não decisão → só 1
        # vigente por repo (antes acumulava 1 cópia por subida — 55 no PoC).
        from roboto.app.repo_profile import build_repo_profile

        _profile = build_repo_profile(f"/work/{config.default_repo}")
        if _profile:
            await store.remember(
                config.tenant, _profile, kind="perfil", ref=config.default_repo,
                now=_now(), unique_by_ref=True,
            )

        async def _run_refine() -> None:
            # refino engine-scoped (Fatia 6/C): o motor LÊ o repo e propõe a issue (feed ao vivo)
            await process_refine_tick(
                refiner_engine, store, adapters.github,
                tenant=config.tenant, chat_id=config.chat_id, now=_now,
                tavily_key=config.tavily_api_key, gateway=adapters.gateway,
                decider=refine_decider, code_intel=config.code_intel,
                persona=config.refine_persona,
            )

        async def _run_claude() -> None:
            # ciclo completo: motor->git->PR->review(≠autor)->correção. Merge = gate humano (D7).
            await process_pr_run_tick(
                claude,
                adapters.gateway,
                adapters.github,
                store,
                tenant=config.tenant,
                workdir_root="/work",
                reviewer="review",
                git_factory=lambda ws: SubprocessGit(ws),
                now=_now,
                base=config.base_branch,
                wip_limit=config.wip_limit,  # backpressure (J)
                self_assign_login=config.bot_login,  # self-assign ao assumir (#150)
                persona=config.impl_persona,  # âncora de papel (A/B atrás de flag)
            )

        async def _run_scope() -> None:
            # motor escaneia o repo (leitura) e monta a issue -> proposta no Telegram (G/F/I)
            await process_scope_tick(
                claude, store, tenant=config.tenant, workdir_root="/work", now=_now
            )

        async def _close_merged() -> None:
            # Sem webhook local: nada avisa que o PR foi mergeado/fechado, então o run fica preso
            # em VERIFYING (ATIVO → segura lock/WIP). Reconcilia contra o PR real: mergeado → DONE,
            # fechado-sem-merge → ABANDONED. Cobre impl (execution_pr) E correct (issue_id = PR).
            from roboto.app.reconcile import reconcile_verifying

            await reconcile_verifying(store, adapters.github, tenant=config.tenant, now=_now())

        async def _run_correct() -> None:
            # B: corrige um PR já aberto conforme o review (no branch do PR). reviewer≠autor.
            await process_correct_tick(
                claude, adapters.gateway, adapters.github, store,
                tenant=config.tenant, workdir_root="/work", reviewer="review",
                git_factory=lambda ws: SubprocessGit(ws), now=_now, base=config.base_branch,
            )

        async def _run_revert() -> None:
            # H: recuperação git-first — reverte o PR da execução e reabre a issue (merge humano).
            from roboto.app.revert import process_revert_tick

            await process_revert_tick(
                adapters.github, store,
                tenant=config.tenant, workdir_root="/work",
                git_factory=lambda ws: SubprocessGit(ws), now=_now, base=config.base_branch,
            )

        # gatilho por POLLING (#166): sem webhook, o daemon detecta PR estabilizado (debounce) e
        # enfileira um `correct` (re-review → corrige/avisa). Debounce via env (default 30 min).
        from roboto.app.pr_poll import process_pr_poll_tick

        poll_repos = sorted(config.repos) or [config.default_repo]
        poll_debounce = int(os.environ.get("ROBOTO_PR_POLL_DEBOUNCE", "1800"))

        async def _run_pr_poll() -> None:
            await process_pr_poll_tick(
                adapters.github, store, tenant=config.tenant, repos=poll_repos,
                now=_now, debounce_seconds=poll_debounce,
            )

        # projeção do estado da issue -> label `estado:*` no GitHub (#161). Estado canônico = run
        # mais recente da issue; GitHub é adapter. `_label_seen` deduplica por processo.
        from roboto.app.issue_state import project_issue_labels_tick

        _label_seen: dict[tuple[str, str], str] = {}

        async def _run_labels() -> None:
            await project_issue_labels_tick(
                adapters.github, store, tenant=config.tenant, now=_now, seen=_label_seen
            )

        # gatilho por comentário `@potter <comando>` (#166): polling, anti-loop por marcador.
        from roboto.app.comment_poll import process_comment_poll_tick

        async def _run_comments() -> None:
            await process_comment_poll_tick(
                adapters.github, store, tenant=config.tenant, repos=poll_repos, now=_now
            )

        tasks.append(run_periodic(_run_claude, 5.0, stop))
        tasks.append(run_periodic(_run_scope, 5.0, stop))
        tasks.append(run_periodic(_run_refine, 5.0, stop))
        tasks.append(run_periodic(_run_correct, 5.0, stop))
        tasks.append(run_periodic(_run_revert, 5.0, stop))
        tasks.append(run_periodic(_run_pr_poll, 60.0, stop))
        tasks.append(run_periodic(_run_comments, 30.0, stop))
        tasks.append(run_periodic(_run_labels, 20.0, stop))
        tasks.append(run_periodic(_close_merged, 15.0, stop))

    await asyncio.gather(*tasks)


async def _run_setup(store: Store, bootstrap: dict[str, str]) -> None:
    """Serve o cockpit em modo setup até a config ficar completa (reload_event)."""
    import uvicorn

    reload_event = asyncio.Event()
    app = build_setup_app(
        store,
        token=bootstrap.get("CONSOLE_TOKEN", ""),
        bootstrap=bootstrap,
        reload_event=reload_event,
        now=_now,
    )
    if not bootstrap.get("CONSOLE_TOKEN"):
        print("AVISO: CONSOLE_TOKEN ausente — a tela de setup não poderá salvar. Defina-o no env.")
    print(f"modo setup: abra http://<host>:{_PORT} e configure (precisa do CONSOLE_TOKEN).")
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=_PORT, log_level="info"))

    async def _watch() -> None:
        await reload_event.wait()
        server.should_exit = True  # config salva -> encerra o setup; o main recarrega

    await asyncio.gather(server.serve(), _watch())


async def main() -> int:
    env = os.environ
    database_url = env.get("DATABASE_URL")
    if not database_url:
        print("config inválida: defina DATABASE_URL (bootstrap)")
        return 1

    store = await PostgresStore.connect(database_url)
    try:
        # semeia o .env no banco (origem env vira registro; o banco é a fonte única — trilha O)
        seed = settable_from_env(env)
        if seed:
            await store.set_app_config(seed, _now())
        bootstrap = {k: env[k] for k in BOOTSTRAP_KEYS if env.get(k)}

        while True:
            stored = await store.get_app_config()
            # bootstrap (DATABASE_URL/CONSOLE_TOKEN) sobre o banco (fonte única da config)
            loaded = load_config({**stored, **bootstrap})
            if isinstance(loaded, Err):
                print(f"modo setup: {loaded.error.message}")
                await _run_setup(store, bootstrap)
                continue  # config salva pela tela -> recarrega e reavalia
            await _run_daemon(loaded.value, store)
            return 0
    finally:
        await store.close()
