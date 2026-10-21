"""Issue escaneada pelo MOTOR (G/F/I): o Claude Code explora o repo em LEITURA e monta a issue.

Em vez do chat barato montar a issue às cegas, o motor lê o projeto (AGENTS.md, código via
code-intel/ripgrep, issues) e produz um rascunho FUNDAMENTADO. Depois: a mesma proposta→OK (D30).
Roda como um RUN (agent="scope") num laço próprio — não bloqueia o poll do Telegram.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from roboto.agents.refiner import IssueDraft, _parse_draft
from roboto.app.refine import _SEED, propose_issue
from roboto.engines.port import CodingEngine, EngineEventKind, RunSpec
from roboto.orchestrator.model import Run
from roboto.orchestrator.store import Store
from roboto.result import Ok

_COST_PER_MTOK = 0.4  # custo aprox. Qwen/OpenRouter — medir/afinar (L)

_SCOPE_PROMPT = (
    "Você está MONTANDO uma issue (NÃO vai codar agora, NÃO edite arquivos). "
    "Explore o repo {repo} (cwd {workdir}) em modo LEITURA: entenda o contexto relevante "
    "(AGENTS.md, código, issues). Economia de token (F): use code-intel (símbolos/refs) e ripgrep "
    "(texto literal) — não leia arquivos inteiros à toa.\n\n"
    "Pedido do humano:\n{idea}\n\n"
    "Memória do projeto (fatos/decisões anteriores — use se relevante):\n{memory}\n\n"
    "Produza uma ISSUE acionável (DoR), respondendo SÓ neste formato, sem texto extra:\n"
    "TITLE: <título curto em Conventional Commits>\n"
    "BODY:\n## Contexto\n<por quê, com base no repo real>\n"
    "## Escopo\n<arquivos/áreas REAIS do repo>\n"
    "## Critérios de aceite\n- [ ] <verificável>\n"
    "## DoD\n- [ ] testes · lint/typecheck · review · CI\n## Fora de escopo\n<...>"
)


async def run_scope(
    engine: CodingEngine, run: Run, *, idea: str, workdir: str, store: Store, now: datetime
) -> IssueDraft:
    """Roda o motor em leitura pra transformar a ideia num rascunho fundamentado no repo."""
    # second brain (trilha G): recall determinístico (FTS, sem LLM) dos fatos/decisões relevantes
    facts = await store.recall(run.tenant, idea, 5)
    memory = "\n".join(f"- [{f.kind}] {f.text}" for f in facts) or "(sem fatos registrados ainda)"
    prompt = _SCOPE_PROMPT.format(repo=run.repo, workdir=workdir, idea=idea, memory=memory)
    started = await engine.start(
        RunSpec(tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt)
    )
    parts: list[str] = []
    tin = tout = 0
    async for ev in engine.events():
        if ev.kind is EngineEventKind.MESSAGE:
            parts.append(ev.text)
        elif ev.kind is EngineEventKind.FINISHED:
            tin, tout = ev.tokens_in, ev.tokens_out
    session = await store.create_session(run.tenant, run.id, engine.engine, now)
    native = getattr(engine, "session_id", "") or (started.value if isinstance(started, Ok) else "")
    if native:
        await store.set_native_session(session.id, native, now)
    await store.record_llm_call(
        tenant=run.tenant, run_id=run.id, provider="openrouter", model="qwen/qwen3-coder",
        tier="frontier", tokens_in=tin, tokens_out=tout,
        cost_usd=(tin + tout) / 1_000_000 * _COST_PER_MTOK, now=now,
    )
    return _parse_draft("\n".join(parts))


async def process_scope_tick(
    engine: CodingEngine, store: Store, *, tenant: str, workdir_root: str,
    now: Callable[[], datetime], lease_seconds: int = 1800,
) -> None:
    """Pega o próximo run de scope, deixa o motor montar a issue e PROPÕE (aguarda o OK humano)."""
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds, agent="scope")
    if run is None:
        return
    idea = ""
    for it in await store.interactions_for_execution(run.id):
        if it.prompt == _SEED:
            idea = it.answer or ""
            break
    workdir = f"{workdir_root}/{run.repo}"
    draft = await run_scope(engine, run, idea=idea, workdir=workdir, store=store, now=moment)
    await propose_issue(run, draft, chat_id=run.origin_chat_id or "", store=store, now=moment)
