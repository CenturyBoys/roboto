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
from roboto.agents.review import (
    PullRequest,
    ReviewVerdict,
    check_issue_readiness,
    montar_review,
    revisar_pr,
)
from roboto.app.comment_poll import BOT_MARKER
from roboto.app.correction import CycleResult, correction_cycle
from roboto.app.deps import blocked_by
from roboto.app.engine_loop import guarded_events
from roboto.app.jev_guard import assess as assess_risk
from roboto.app.memory import recall_block
from roboto.app.repo_profile import build_repo_profile, read_agents_conventions
from roboto.app.secret_scan import SecretLeakError, scan_diff
from roboto.app.task_class import TaskType, classificar_task
from roboto.app.tiering import classificar_tier
from roboto.app.transient import is_transient
from roboto.app.verify import VerifyResult, arquivos_ts, secao_verify, verificar
from roboto.engines.port import CodingEngine, EngineEventKind, RunSpec
from roboto.github.app import IssueRef
from roboto.llm.port import ModelGateway
from roboto.orchestrator.core import backoff_until
from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result

_COST_PER_MTOK = 0.4  # custo aprox. Qwen/OpenRouter ($/milhão de tokens) — medir/afinar (L)
_MAX_RUN_ATTEMPTS = 3  # teto de re-tentativas em erro transitório (B) antes de FAILED terminal


class GitOps(Protocol):
    async def prepare_branch(self, name: str) -> None: ...
    async def checkout_remote(self, name: str) -> None: ...  # entra na branch REMOTA do PR (B)
    async def commit_all(self, message: str) -> None: ...
    async def push(self, name: str) -> None: ...
    # mensagens dos commits da branch vs base — vira a "história da implementação" no corpo do PR
    async def log_since(self, base: str) -> str: ...
    # diff unificado da branch vs base — alimenta o secret-scan antes do push (H)
    async def diff(self, base: str) -> str: ...
    # reverte os commits de source_branch numa revert_branch nova (recuperação git-first, H)
    async def revert_range(self, base: str, source_branch: str, revert_branch: str) -> bool: ...


class GithubPrOps(Protocol):
    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]: ...

    # branch head do PR — p/ corrigir um PR já aberto (B)
    async def get_pr_head(self, repo: str, number: int) -> Result[str, Error]: ...

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]: ...

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main"
    ) -> Result[IssueRef, Error]: ...

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]: ...

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]: ...

    # abre/fecha a issue — reverter um PR reabre a issue p/ o fleet refazer (recuperação, H)
    async def set_issue_state(
        self, repo: str, number: int, state: str
    ) -> Result[None, Error]: ...

    # estado de uma issue ("open"/"closed") — gate de dependência (J): não codar bloqueada
    async def get_issue_state(self, repo: str, number: int) -> Result[str, Error]: ...

    # fleet "levanta a mão": self-assign ao pegar a task (#150) — best-effort
    async def add_assignee(
        self, repo: str, number: int, login: str
    ) -> Result[None, Error]: ...

    async def submit_review(
        self, repo: str, number: int, body: str, comments: list[tuple[str, int, str]]
    ) -> Result[None, Error]: ...


async def _guard_secrets(
    git: GitOps, base: str, *, store: Store | None, run: Run, now: datetime | None
) -> str | None:
    """Gate de segredo (H): varre o diff LOCAL antes do push. Se achar credencial, registra no feed
    e DEVOLVE o resumo (o chamador decide: auto-corrigir ou abortar). O segredo nunca é enviado —
    o push só acontece depois que a varredura volta limpa. Sem vazamento → ``None``."""
    leaks = scan_diff(await git.diff(base))
    if not leaks:
        return None
    resumo = "; ".join(f"{leak.pattern} [{leak.redacted}]" for leak in leaks)
    if store is not None and now is not None:
        await store.append_session_event(
            run.tenant, run.id, "message", now,
            text=f"🔒 secret-scan bloqueou o push: possível segredo no diff — {resumo}.",
        )
    return resumo


# tentativas de AUTO-CORREÇÃO de segredo (H): o motor recebe o bloqueio e troca o literal por
# placeholder/env; re-escaneia. Esgotou → aborta (SecretLeakError = último recurso).
_SECRET_FIX_ATTEMPTS = 2


def _secret_fix_prompt(resumo: str) -> str:
    return (
        "O secret-scan BLOQUEOU o push: o diff contém algo com cara de segredo/credencial — "
        f"{resumo}. NÃO é permitido versionar segredo, nem de exemplo. Corrija AGORA: substitua o "
        "literal por um PLACEHOLDER claramente falso (ex.: 'xxx.yyy.zzz', 'REDACTED') ou leia de "
        "variável de ambiente/fixture. Mantenha o resto da implementação. Em teste de "
        "redação, um token FAKE serve igual. Edite os arquivos e pare (não faça commit nem push)."
    )


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
    allow_secret: bool = False,  # override humano (H): libera o push mesmo com secret-scan positivo
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
        risk_md = await _risk_section()
        if risk_md:
            parts.append(risk_md)
        parts.append(f"_Gerado pelo fleet roboto (run {run.id}). Revisar antes do merge._")
        return "\n\n".join(parts)

    async def _risk_section() -> str:
        # risco determinístico (jev-guard, H) pelos arquivos tocados. Só surfa médio/alto — não
        # polui PR trivial e NÃO bloqueia (o gate segue sendo o merge humano).
        try:
            files = await git.changed_files(base)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — best-effort
            return ""
        risk = assess_risk(files)
        if risk.level == "baixo":
            return ""
        emoji = "🔴" if risk.level == "alto" else "🟡"
        motivos = "".join(f"\n- {r}" for r in risk.reasons)
        return (
            f"## {emoji} Risco: {risk.level}{motivos}\n\n"
            "_Risco determinístico (jev-guard) pelos arquivos tocados — olhe com atenção no merge._"
        )

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
    # convenções do repo-alvo (E, determinismo primeiro): o harness LÊ o AGENTS.md e injeta — não
    # manda o motor "ler sozinho" (gasta token F e pode ignorar). Capado pelo orçamento de token.
    conventions = read_agents_conventions(workdir)
    conventions_block = f"\n{conventions}\n" if conventions else ""
    # second brain (G): o harness recalla decisões/fatos relevantes e injeta — continuidade entre
    # runs sem sessão gigante. Recall determinístico (FTS/overlap), capado por orçamento (F).
    memory = await recall_block(store, run.tenant, f"{pr_title} {contexto}") if store else ""
    memory_block = (
        f"\nMEMÓRIA RELEVANTE (second brain — decisões/fatos anteriores):\n{memory}\n"
        if memory
        else ""
    )
    # aprendizado entre TENTATIVAS (B/G): no retry (mesmo run, attempt>0) o motor nasce fresco e
    # poderia recair no mesmo erro. Injeta o MOTIVO da última falha — lido do feed da própria
    # execução (determinístico) — pra ele já começar evitando a causa.
    aprendizado_block = ""
    if store is not None and run.attempt > 0:
        hist = await store.session_events(run.id, 0, 500)
        motivos = [
            e.text for e in hist
            if e.text.startswith("⚠️ execução falhou") or "secret-scan" in e.text.lower()
        ]
        if motivos:
            aprendizado_block = (
                "\nAPRENDIZADO DA TENTATIVA ANTERIOR (esta issue JÁ falhou — NÃO repita a causa):\n"
                f"{motivos[-1]}\n"
                "Já comece evitando isso: se foi secret-scan, use placeholder/env desde o início; "
                "se foi review/checks, atenda o apontamento antes de concluir.\n"
            )
    base_prompt = (
        f"Implemente a issue {run.issue_id} no repo {run.repo} (cwd {workdir}).{contexto}"
        f"{profile_block}{conventions_block}{memory_block}{aprendizado_block}\n"
        "ESCOPO MÍNIMO: entregue APENAS o que os Critérios de aceite da issue pedem — nada além. "
        "NÃO crie documentos/arquivos extras (ex.: breakdown ou 'update' de épico), NÃO edite o "
        "épico nem outras issues, NÃO toque em código não relacionado, NÃO commite lockfile/deps "
        "sem a issue exigir. Se identificar trabalho FUTURO (quebrar épico, abrir sub-issues), "
        "apenas MENCIONE no fim — NÃO crie arquivo nem issue por conta própria. "
        "Siga TODAS as regras do AGENTS.md — inclusive doc-in-sync (§5): mudança de regra/domínio "
        "exige atualizar a doc (.md/docs/ADR) no MESMO commit. "
        "Rode os checks do repo (lint, typecheck, testes, doc-sync) e corrija até passarem "
        "ANTES de concluir. "
        "NÃO abra PR, NÃO rode `git push`, `gh pr create` nem a API de PR do GitHub — o FLEET faz "
        "isso por você (commit + push + PR). Só IMPLEMENTE e deixe os arquivos prontos; abrir PR "
        "aqui cria PR DUPLICADO. "
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
    coder: dict[str, str] = {}  # id NATIVO da sessão do coder, p/ RESUMIR na correção (= contexto)

    async def _engine_turn(prompt: str, resume: str | None) -> None:
        # um turno do motor: edita o repo, alimenta o feed ao vivo (Fatia 2) e mede o token (D10/L).
        spec = RunSpec(
            tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt,
            model=modelo_do_motor, resume_session_id=resume,
        )
        started = await engine.start(spec)
        native = getattr(engine, "session_id", "") or (
            started.value if isinstance(started, Ok) else ""
        )
        if native:
            coder["native"] = native  # fixa p/ a próxima correção resumir o MESMO contexto
        tin = tout = 0
        async for event in guarded_events(engine.events()):  # deixa o motor editar o repo
            if store is not None and now is not None:
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
            session = await store.create_session(run.tenant, run.id, engine.engine, now)
            if native:
                await store.set_native_session(session.id, native, now)
            await store.record_llm_call(
                tenant=run.tenant, run_id=run.id, provider="openrouter",
                model="qwen/qwen3-coder", tier="frontier", tokens_in=tin, tokens_out=tout,
                cost_usd=(tin + tout) / 1_000_000 * _COST_PER_MTOK, now=now,
            )

    async def implement(feedback: list[str]) -> PullRequest:
        prompt = base_prompt
        if feedback:
            prompt += "\nCorrija os pontos do review:\n- " + "\n- ".join(feedback)
        # correção RESUMINDO a sessão do coder: 1ª tentativa é sessão nova; correções resumem.
        await _engine_turn(prompt, coder.get("native") if feedback else None)
        await git.prepare_branch(branch)
        await git.commit_all(title if not feedback else f"{title} (correção)")
        # H: secret-scan com AUTO-CORREÇÃO — bloqueia o push e devolve ao motor p/ trocar o literal
        # por placeholder/env, re-escaneando. Esgotou → aborta (o push nunca sai com segredo).
        leak = await _guard_secrets(git, base, store=store, run=run, now=now)
        fixes = 0
        while leak and fixes < _SECRET_FIX_ATTEMPTS:
            fixes += 1
            if store is not None and now is not None:
                await store.append_session_event(
                    run.tenant, run.id, "message", now,
                    text=f"↻ secret-scan: motor vai remover o literal (tentativa {fixes}).",
                )
            await _engine_turn(_secret_fix_prompt(leak), coder.get("native"))
            await git.commit_all("remove literal com cara de segredo (secret-scan)")
            leak = await _guard_secrets(git, base, store=store, run=run, now=now)
        if leak and not allow_secret:
            raise SecretLeakError(leak)  # persistiu após auto-correção → terminal (último recurso)
        if leak and allow_secret and store is not None and now is not None:
            # override humano (B): operador marcou falso-positivo — libera, mas AUDITA no feed
            await store.append_session_event(
                run.tenant, run.id, "message", now,
                text=f"⚠️ secret-scan OVERRIDE humano: push liberado apesar de — {leak}",
            )
        # #144: diff vazio = motor não editou nada → FALHA explícita (não revisa "o nada").
        if not (await git.diff(base)).strip():
            raise RuntimeError("motor não editou nada (diff vazio vs base) — nada a revisar")
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
                # #144: open_pr falho NÃO vira PR nº 0 silencioso — propaga e FALHA o run (senão o
                # review rodava sobre diff vazio e dava veredito sem valor).
                if isinstance(opened, Err):
                    raise RuntimeError(
                        f"open_pr falhou (PAT sem 'Pull requests: write'?): {opened.error}"
                    )
                state["pr"] = opened.value.number
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
        # review ESTRUTURADO (Trilha D): findings tipados → inline enxuto (<details> p/ evidência).
        strategy = os.environ.get("ROBOTO_REVIEW_STRATEGY", "single")
        res = await revisar_pr(
            pr, review_gw, reviewer=reviewer, verify_findings=achados, strategy=strategy
        )
        findings = res.value if isinstance(res, Ok) else []
        inline, body, aprovado = montar_review(findings)
        if isinstance(await github.submit_review(run.repo, pr.number, body, inline), Err):
            await github.comment_pr(run.repo, pr.number, body)  # linhas fora do diff → só o resumo
        # feedback RICO p/ a correção: severidade + título + local + recomendação de cada finding
        issues = [
            f"[{f.severidade}] {f.titulo} ({f.arquivo}:{f.linha}) — {f.recomendacao}"
            for f in findings
        ]
        return ReviewVerdict(approved=aprovado, issues=issues, summary=body[:200])

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
    wip_limit: int = 0,  # backpressure (J): cap de runs ativos por tenant; 0 = sem limite
    self_assign_login: str = "",  # #150: login do fleet p/ self-assign; "" = não atribui
) -> None:
    """Pega o próximo run da fila e roda o ciclo. Aprovado -> VERIFYING; desistiu -> FAILED.

    Recuperável (não se perde): run keyed no banco; em restart, lease expira -> sweeper re-enfileira
    -> reprocessa (branch força-push, PR reaproveitado via find_open_pr). Merge = gate humano (D7).
    """
    moment = now()
    run = await store.claim_next_queued(
        tenant, moment, lease_seconds, agent="impl", wip_limit=wip_limit
    )
    if run is None:
        return

    # #150: o fleet "levanta a mão" — self-assign da issue ao assumir (best-effort, não derruba).
    if self_assign_login and run.issue_id.isdigit():
        await github.add_assignee(run.repo, int(run.issue_id), self_assign_login)

    # gate de prontidão ANTES de implementar: issue esqueleto -> pede ao humano, NÃO chuta (D28)
    if run.issue_id.isdigit():
        issue = await github.get_issue(run.repo, int(run.issue_id))
        if isinstance(issue, Ok):
            title, body = issue.value
            # gate de DEPENDÊNCIA (J): "blocked by #N" e a #N ainda ABERTA → não coda, espera.
            # Serializa o que colide (ex.: #220 depende do #79) e evita codar sobre o inexistente.
            for bloq in blocked_by(f"{title}\n{body}"):
                st = await github.get_issue_state(run.repo, bloq)
                if isinstance(st, Ok) and st.value == "open":
                    await github.comment_pr(
                        run.repo, int(run.issue_id),
                        f"Bloqueada por #{bloq} (ainda aberta) — não implemento até ela fechar.",
                    )
                    await store.set_state(run.id, RunState.WAITING, moment)
                    return
            # gate anti-codar-definição (#158): task de DEFINIÇÃO não vira código — seu "done" é a
            # spec aprovada. Só bloqueia quando a classificação é CONFIANTE (keyword); "sem critério
            # + sem keyword" é ambíguo (dev incompleto) → deixa o gate de DoR pedir pra completar.
            tclass = classificar_task(title, body)
            if tclass.task_type is TaskType.DEFINICAO and tclass.confianca == "alta":
                await github.comment_pr(
                    run.repo, int(run.issue_id),
                    "Esta é uma task de **definição** (produz spec/decisão, não código) — não vou "
                    f"implementar. Sinais: {', '.join(tclass.sinais)}. 'Done' = spec aprovada.",
                )
                await store.set_state(run.id, RunState.WAITING, moment)
                return
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
    # override humano do secret-scan (B): operador liberou este run (FP) → ciclo não aborta no scan
    secret_ok = await store.is_secret_allowed(run.id)
    try:
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
            allow_secret=secret_ok,
        )
    except Exception as exc:  # noqa: BLE001 — motor travado (watchdog) / git / PR: tira de RUNNING
        # Erro TRANSITÓRIO de provedor (402 sem crédito, 429, 5xx, overloaded) → re-enfileira com
        # backoff (B): quando a condição passa (ex.: humano recarrega), o daemon retoma SOZINHO. Só
        # vira FAILED terminal se não-transitório ou se estourar o teto de tentativas.
        nxt = run.attempt + 1
        if is_transient(str(exc)) and nxt < _MAX_RUN_ATTEMPTS:
            await store.requeue_run_with_backoff(run.id, nxt, backoff_until(nxt, moment), moment)
            await store.append_session_event(
                run.tenant, run.id, "message", moment,
                text=f"⏳ erro transitório (provedor) — re-enfileirado (tentativa {nxt}) com "
                f"backoff; retoma sozinho quando passar: {exc}",
            )
            return
        await store.set_state(run.id, RunState.FAILED, moment)
        await store.append_session_event(
            run.tenant, run.id, "message", moment, text=f"⚠️ execução falhou: {exc}"
        )
        return
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


def _correct_prompt(repo: str, pr_number: int, workdir: str, issues: list[str]) -> str:
    return (
        f"Corrija os APONTAMENTOS do review no PR #{pr_number} do repo {repo} (cwd {workdir}). "
        "Você está NA branch do PR, com o código já implementado — faça SÓ os ajustes abaixo, sem "
        "reimplementar nem sair do escopo. Rode os checks do repo e corrija até passarem ANTES de "
        "concluir. Pontos do review:\n- " + "\n- ".join(issues)
    )


async def process_correct_tick(
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
    lease_seconds: int = 3600,
) -> None:
    """B — corrige um PR JÁ ABERTO conforme o review, no PRÓPRIO branch do PR. `run.issue_id`
    carrega o NÚMERO do PR. Fluxo: checkout da branch do PR (contexto do PR, não da base) → review
    independente (revisor≠autor) → se reprova, o motor corrige os apontamentos → commit → force-push
    (atualiza o MESMO PR) → re-review → comenta. Merge = gate humano (D7)."""
    moment = now()
    run = await store.claim_next_queued(tenant, moment, lease_seconds, agent="correct")
    if run is None:
        return
    if not run.issue_id.isdigit():
        await store.set_state(run.id, RunState.FAILED, moment)
        return
    pr_number = int(run.issue_id)
    workdir = f"{workdir_root}/{run.repo}"
    git = git_factory(workdir)

    async def _review_now() -> ReviewVerdict:
        diff = await github.get_pr_diff(run.repo, pr_number)
        pr = PullRequest(
            number=pr_number,
            author=str(engine.engine),
            title=f"PR #{pr_number}",
            diff=diff.value if isinstance(diff, Ok) else "",
        )
        res = await revisar_pr(pr, gateway, reviewer=reviewer)
        findings = res.value if isinstance(res, Ok) else []
        issues = [f"[{f.severidade}] {f.titulo} — {f.recomendacao}" for f in findings]
        from roboto.agents.review import aprovado_por_findings

        return ReviewVerdict(approved=aprovado_por_findings(findings), issues=issues)

    try:
        head = await github.get_pr_head(run.repo, pr_number)
        if not isinstance(head, Ok) or not head.value:
            raise RuntimeError(f"PR #{pr_number} sem branch head")
        branch = head.value
        await git.checkout_remote(branch)  # estado do PR na árvore ANTES de editar (B: seguro)

        verdict = await _review_now()
        if verdict.approved:
            await github.comment_pr(
                run.repo, pr_number, "✅ Correção: nada a ajustar — o review já está aprovado."
            )
            await store.append_session_event(
                run.tenant, run.id, "message", moment, text="✅ review aprovado — nada a corrigir"
            )
            await store.set_state(run.id, RunState.DONE, moment)
            return

        # motor corrige NA branch do PR (código já implementado) com os apontamentos do review
        prompt = _correct_prompt(run.repo, pr_number, workdir, verdict.issues)
        await engine.start(
            RunSpec(tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt)
        )
        tin = tout = 0
        async for event in guarded_events(engine.events()):  # feed ao vivo no cockpit
            if event.kind is EngineEventKind.MESSAGE and event.text:
                await store.append_session_event(
                    run.tenant, run.id, "message", moment, text=event.text
                )
            elif event.kind is EngineEventKind.TOOL_CALL:
                await store.append_session_event(
                    run.tenant, run.id, "tool_call", moment, tool=event.tool
                )
            elif event.kind is EngineEventKind.FINISHED:
                tin, tout = event.tokens_in, event.tokens_out
        # custo do coder da correção (L): sem isto o run de correct aparecia com custo 0 no cockpit
        await store.record_llm_call(
            tenant=run.tenant, run_id=run.id, provider="openrouter", model="qwen/qwen3-coder",
            tier="frontier", tokens_in=tin, tokens_out=tout,
            cost_usd=(tin + tout) / 1_000_000 * _COST_PER_MTOK, now=moment,
        )

        await git.commit_all(f"fix(review): corrige apontamentos do review (PR #{pr_number})")
        leak = await _guard_secrets(git, base, store=store, run=run, now=moment)  # H: antes do push
        if leak:
            raise SecretLeakError(leak)  # correção vazou segredo → bloqueia (push nunca sai sujo)
        await git.push(branch)  # force-push atualiza o MESMO PR

        again = await _review_now()
        body = (
            "✅ Correção aplicada — review re-aprovado."
            if again.approved
            else "🔁 Correção aplicada; ainda restam pontos:\n- " + "\n- ".join(again.issues)
        )
        await github.comment_pr(
            run.repo, pr_number, body + f"\n\n_(correção do fleet, reviewer≠autor)_\n{BOT_MARKER}"
        )
        final = RunState.VERIFYING if again.approved else RunState.FAILED
        await store.set_state(run.id, final, moment)
    except Exception as exc:  # noqa: BLE001 — falha não pode deixar o run preso em RUNNING
        await store.set_state(run.id, RunState.FAILED, moment)
        await store.append_session_event(
            run.tenant, run.id, "message", moment, text=f"⚠️ correção falhou: {exc}"
        )
