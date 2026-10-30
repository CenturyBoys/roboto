"""Amarração do ciclo issue→dev→PR→review→correção no fluxo real (D28 + máquina de estados).

Liga as peças: o **motor** edita o repo → **git** (branch/commit/push) → **PR** no GitHub →
**review(≠autor)** sobre o diff → **comentário** → se reprovado, re-implementa com o feedback
(`correction_cycle`). `git`/`github` são portas (fakes no teste; `SubprocessGit`/`GithubAppClient`
no real). Aprovação NÃO mergeia — gate humano (D7).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import PullRequest, ReviewVerdict, check_issue_readiness, review_pr
from roboto.app.correction import CycleResult, correction_cycle
from roboto.app.repo_profile import build_repo_profile
from roboto.app.tiering import classificar_tier
from roboto.app.verify import VerifyResult, arquivos_ts, secao_verify, verificar
from roboto.engines.port import CodingEngine, EngineEventKind, RunSpec
from roboto.github.app import IssueRef
from roboto.llm.port import ModelGateway
from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result

_COST_PER_MTOK = 0.4  # custo aprox. Qwen/OpenRouter ($/milhão de tokens) — medir/afinar (L)


class GitOps(Protocol):
    async def prepare_branch(self, name: str) -> None: ...
    async def commit_all(self, message: str) -> None: ...
    async def push(self, name: str) -> None: ...
    # mensagens dos commits da branch vs base — vira a "história da implementação" no corpo do PR
    async def log_since(self, base: str) -> str: ...


class GithubPrOps(Protocol):
    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]: ...

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]: ...

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main"
    ) -> Result[IssueRef, Error]: ...

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]: ...

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]: ...


async def run_pr_cycle(
    *,
    engine: CodingEngine,
    gateway: ModelGateway,
    github: GithubPrOps,
    git: GitOps,
    run: Run,
    workdir: str,
    reviewer: str,
    base: str = "main",
    max_attempts: int = 3,
    store: Store | None = None,
    now: datetime | None = None,
) -> CycleResult:
    branch = f"roboto/run-{run.id}"
    # título/corpo do PR seguem a ISSUE (não "run 1: 107"): título = título da issue; corpo linka
    # `Closes #N` — alinha com a convenção do repo. Injeta o CORPO no prompt (requisitos) — senão o
    # motor só vê o número e se perde. Falha graciosa se o GitHub não responder.
    contexto = ""
    pr_title = f"issue #{run.issue_id}"
    if run.issue_id.isdigit():
        got = await github.get_issue(run.repo, int(run.issue_id))
        if isinstance(got, Ok):
            issue_title, issue_body = got.value
            pr_title = issue_title.strip() or pr_title
            contexto = f"\n\nTítulo: {issue_title}\nRequisitos (corpo da issue):\n{issue_body}\n"
    title = pr_title
    closes = f"Closes #{run.issue_id}" if run.issue_id.isdigit() else ""

    # right-sizing do motor por CLASSE de tarefa (D/F, determinístico): tarefa grande/arquitetural
    # roda no tier FORTE (ROBOTO_STRONG_MODEL, default Sonnet); pequena fica no motor barato (qwen,
    # modelo "" = default do ccr). Classificador em app/tiering.py — não é decisão de LLM.
    decisao_tier = classificar_tier(pr_title, contexto or run.issue_id)
    # id no formato "provider,model": o ccr IGNORA o model do cliente e roteia pela config, MENOS
    # quando vem com a sintaxe de override "provider,model" — aí usa esse (validado no PoC).
    modelo_forte = os.environ.get("ROBOTO_STRONG_MODEL", "openrouter,anthropic/claude-sonnet-4.6")
    modelo_do_motor = modelo_forte if (decisao_tier.forte and modelo_forte) else ""
    print(
        f"[tier] forte={decisao_tier.forte} modelo={modelo_do_motor or '(default/qwen)'} "
        f"— {decisao_tier.motivo}"
    )

    async def build_pr_body() -> str:
        # corpo do PR = objetivo da issue + a HISTÓRIA da implementação (assuntos dos commits que o
        # motor escreveu). Montado DEPOIS dos commits, pra o log existir. Conta o que foi feito.
        story = ""
        try:
            story = (await git.log_since(base)).strip()
        except Exception:  # noqa: BLE001 — log é best-effort; corpo degrada p/ só o objetivo
            story = ""
        parts = [p for p in (closes, f"## Objetivo\n{pr_title}") if p]
        if story:
            parts.append(f"## O que foi feito\n{story}")
        verify_md = await _verify_section()
        if verify_md:
            parts.append(verify_md)
        parts.append(f"_Gerado pelo fleet roboto (run {run.id}). Revisar antes do merge._")
        return "\n\n".join(parts)

    verify_cache: dict[str, VerifyResult] = {}  # último resultado do verify (reusado no review)

    async def _run_verify() -> VerifyResult | None:
        # verify determinístico (code-intel/tsgo, sem script): erros de tipo introduzidos vs a base.
        # Best-effort — nunca derruba o ciclo. Cacheia p/ o review reusar (ideia 1) sem recomputar.
        try:
            changed = arquivos_ts(await git.changed_files(base))  # type: ignore[attr-defined]
            if not changed:
                res = VerifyResult(True, [])
            else:
                pares = [(f, await git.show(f"origin/{base}", f)) for f in changed]  # type: ignore[attr-defined]
                cmd = os.environ.get("ROBOTO_CODE_INTEL_CMD", "code-intel-mcp")
                res = await asyncio.to_thread(verificar, workdir, pares, cmd=cmd)
            verify_cache["last"] = res
            return res
        except Exception:  # noqa: BLE001 — verify é best-effort
            return None

    async def _verify_section() -> str:
        res = await _run_verify()
        # (1) só anota quando o verify é CONFIÁVEL (disponivel); senão pula — não polui o PR com
        # falso positivo (ex.: tsconfig do monorepo não resolvido pelo code-intel).
        return secao_verify(res) if (res is not None and res.disponivel) else ""
    # perfil do repo (como OPERAR: pm, monorepo, test/lint, deps já instaladas) — pro motor rodar
    # os checks como um dev, sem flailar em "como rodar teste" / sem gambiarra de .cjs.
    profile = build_repo_profile(workdir)
    profile_block = f"\n{profile}\n" if profile else ""
    base_prompt = (
        f"Implemente a issue {run.issue_id} no repo {run.repo} (cwd {workdir}).{contexto}"
        f"{profile_block}\n"
        "ESCOPO MÍNIMO: entregue APENAS o que os Critérios de aceite da issue pedem — nada além. "
        "NÃO crie documentos/arquivos extras (ex.: breakdown ou 'update' de épico), NÃO edite o "
        "épico nem outras issues, NÃO toque em código não relacionado, NÃO commite lockfile/deps "
        "sem a issue exigir. Se identificar trabalho FUTURO (quebrar épico, abrir sub-issues), "
        "apenas MENCIONE no fim — NÃO crie arquivo nem issue por conta própria. "
        "Siga TODAS as regras do AGENTS.md — inclusive doc-in-sync (§5): mudança de regra/domínio "
        "exige atualizar a doc (.md/docs/ADR) no MESMO commit. "
        "Rode os checks do repo (lint, typecheck, testes, doc-sync) e corrija até passarem "
        "ANTES de concluir. "
        "ECONOMIA DE TOKEN (F) — REGRA OBRIGATÓRIA de navegação: para DESCOBRIR onde algo está, "
        "quem usa um símbolo ou o que quebra ao mudá-lo, use SEMPRE as ferramentas do code-intel "
        "(mcp__code-intel__find_symbol, find_references, document_symbols, blast_radius) e o "
        "ripgrep para texto literal — NUNCA leia um arquivo inteiro com Read só para 'procurar'. "
        "Read é "
        "permitido apenas no trecho exato que o code-intel já localizou. Para editar um símbolo "
        "(renomear/mover/alterar corpo), prefira as tools do code-intel (rename_symbol/"
        "replace_symbol_body) a sed/regex. Se você precisa de um símbolo e NÃO chamou o code-intel "
        "antes, está errando."
    )
    state: dict[str, int] = {}  # guarda o número do PR entre tentativas

    async def implement(feedback: list[str]) -> PullRequest:
        prompt = base_prompt
        if feedback:
            prompt += "\nCorrija os pontos do review:\n- " + "\n- ".join(feedback)
        spec = RunSpec(
            tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt, model=modelo_do_motor
        )
        started = await engine.start(spec)
        tin = tout = 0
        async for event in engine.events():  # deixa o motor editar o repo
            if store is not None and now is not None:  # feed ao vivo do cockpit (trilha O, Fatia 2)
                if event.kind is EngineEventKind.MESSAGE and event.text:
                    await store.append_session_event(
                        run.tenant, run.id, "message", now, text=event.text
                    )
                elif event.kind is EngineEventKind.TOOL_CALL:
                    await store.append_session_event(
                        run.tenant, run.id, "tool_call", now, tool=event.tool
                    )
            if event.kind is EngineEventKind.FINISHED:
                tin, tout = event.tokens_in, event.tokens_out
        if store is not None and now is not None:
            # sessão do motor (D23): registra a sessão + o id NATIVO do Claude Code (p/ resume)
            session = await store.create_session(run.tenant, run.id, engine.engine, now)
            native = getattr(engine, "session_id", "") or (
                started.value if isinstance(started, Ok) else ""
            )
            if native:
                await store.set_native_session(session.id, native, now)
            # medição de token (D10/L): uso real do motor
            await store.record_llm_call(
                tenant=run.tenant,
                run_id=run.id,
                provider="openrouter",
                model="qwen/qwen3-coder",
                tier="frontier",
                tokens_in=tin,
                tokens_out=tout,
                cost_usd=(tin + tout) / 1_000_000 * _COST_PER_MTOK,
                now=now,
            )
        await git.prepare_branch(branch)
        await git.commit_all(title if not feedback else f"{title} (correção)")
        await git.push(branch)
        if "pr" not in state:
            # idempotência contra PR vivo: reaproveita o PR aberto do branch, se houver
            existing = await github.find_open_pr(run.repo, branch)
            if isinstance(existing, Ok) and existing.value is not None:
                state["pr"] = existing.value
            else:
                opened = await github.open_pr(
                    run.repo, title=title, body=await build_pr_body(), head=branch, base=base
                )
                state["pr"] = opened.value.number if isinstance(opened, Ok) else 0
        number = state["pr"]
        diff = await github.get_pr_diff(run.repo, number)
        diff_text = diff.value if isinstance(diff, Ok) else ""
        if store is not None and now is not None and number:  # cache p/ o cockpit (Fatia 4)
            url = f"https://github.com/{run.repo}/pull/{number}"
            await store.set_execution_pr(run.id, number, url, diff_text, now)
        return PullRequest(number=number, author=str(engine.engine), title=title, diff=diff_text)

    review_gw: ModelGateway = gateway
    if store is not None and now is not None:  # mede também o review (JUDGE) no llm_call
        from roboto.app.metering import MeteredGateway

        review_gw = MeteredGateway(gateway, store, tenant=run.tenant, run_id=run.id, now=now)

    async def review(pr: PullRequest) -> ReviewVerdict:
        # ideia 1: injeta os achados do verify (code-intel) no review como "possíveis" (avaliar),
        # pra o revisor não aprovar por cima. Reusa o cache do _run_verify (do build_pr_body).
        vr = verify_cache.get("last")
        # só alimenta o review quando o verify é confiável E achou algo (senão None = normal).
        achados = (
            vr.introduzidos if (vr is not None and vr.disponivel and vr.introduzidos) else None
        )
        verdict = await review_pr(pr, review_gw, reviewer=reviewer, verify_findings=achados)
        value = (
            verdict.value
            if isinstance(verdict, Ok)
            else ReviewVerdict(approved=False, issues=["falha ao revisar"])
        )
        if value.approved:
            comment = "✅ Review aprovado."
        else:
            comment = "🔁 Review pediu correções:\n- " + "\n- ".join(value.issues)
        await github.comment_pr(run.repo, pr.number, comment)
        return value

    return await correction_cycle(implement=implement, review=review, max_attempts=max_attempts)


async def process_pr_run_tick(
    engine: CodingEngine,
    gateway: ModelGateway,
    github: GithubPrOps,
    store: Store,
    *,
    tenant: str,
    workdir_root: str,
    reviewer: str,
    git_factory: Callable[[str], GitOps],
    now: Callable[[], datetime],
    base: str = "main",
    lease_seconds: int = 3600,  # ciclo é longo; lease generoso p/ o sweeper não reclamar no meio
) -> None:
    """Pega o próximo run da fila e roda o ciclo. Aprovado -> VERIFYING; desistiu -> FAILED.

    Recuperável (não se perde): run keyed no banco; em restart, lease expira -> sweeper re-enfileira
    -> reprocessa (branch força-push, PR reaproveitado via find_open_pr). Merge = gate humano (D7).
    """
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds, agent="impl")
    if run is None:
        return

    # gate de prontidão ANTES de implementar: issue esqueleto -> pede ao humano, NÃO chuta (D28)
    if run.issue_id.isdigit():
        issue = await github.get_issue(run.repo, int(run.issue_id))
        if isinstance(issue, Ok):
            title, body = issue.value
            verdict = check_issue_readiness(IssueDraft(title=title, body=body))
            if not verdict.ready:
                falta = ", ".join(verdict.missing)
                msg = f"Issue incompleta para dev — falta: {falta}. Complete e eu sigo."
                await github.comment_pr(run.repo, int(run.issue_id), msg)
                if run.origin_chat_id:  # eco no Telegram de quem pediu (D30)
                    await store.enqueue_effect(
                        run.tenant, run.id, "telegram_notify",
                        {"chat_id": run.origin_chat_id,
                         "text": f"⚡ #{run.issue_id}: falta {falta}. Complete a issue e eu sigo."},
                        f"dor-wait:{run.id}", moment,
                    )
                await store.set_state(run.id, RunState.WAITING, moment)
                return

    workdir = f"{workdir_root}/{run.repo}"
    result = await run_pr_cycle(
        engine=engine,
        gateway=gateway,
        github=github,
        git=git_factory(workdir),
        run=run,
        workdir=workdir,
        reviewer=reviewer,
        base=base,
        store=store,  # medição de token (llm_call)
        now=moment,
    )
    await store.set_state(
        run.id, RunState.VERIFYING if result.approved else RunState.FAILED, moment
    )
    if run.origin_chat_id:  # status final volta pro Telegram de quem pediu (D30)
        pr = result.pr
        ref = f" (PR #{pr.number})" if pr is not None else ""
        txt = (
            f"✅ #{run.issue_id}: implementei e o review aprovou{ref}. Falta o merge humano."
            if result.approved
            else f"⚠️ #{run.issue_id}: não aprovei após {result.attempts} tentativa(s){ref}."
        )
        await store.enqueue_effect(
            run.tenant, run.id, "telegram_notify",
            {"chat_id": run.origin_chat_id, "text": txt}, f"done:{run.id}", moment,
        )
