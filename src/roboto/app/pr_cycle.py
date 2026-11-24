"""Amarração do ciclo issue→dev→PR→review→correção no fluxo real (D28 + máquina de estados).

Liga as peças: o **motor** edita o repo → **git** (branch/commit/push) → **PR** no GitHub →
**review(≠autor)** sobre o diff → **comentário** → se reprovado, re-implementa com o feedback
(`correction_cycle`). `git`/`github` são portas (fakes no teste; `SubprocessGit`/`GithubAppClient`
no real). Aprovação NÃO mergeia — gate humano (D7).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
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
from roboto.app.approval_gate import make_policy_callback
from roboto.app.autoformat import autoformat
from roboto.app.ccr_models import pin_or_fallback, registered_models
from roboto.app.ci_triage import (
    ACAO_ABRIR_ISSUE,
    ACAO_CORRIGIR,
    acao_ci,
    changed_files_from_diff,
    ci_issue_body,
    triar_ci,
)
from roboto.app.code_intel_brief import code_intel_brief
from roboto.app.code_intel_diag import code_intel_diagnostics
from roboto.app.code_intel_refs import extract_symbols, symbols_directive
from roboto.app.codebase_map import build_codebase_map
from roboto.app.comment_poll import BOT_MARKER
from roboto.app.correction import CycleResult, correction_cycle
from roboto.app.deps import blocked_by, blocking_labels
from roboto.app.engine_loop import guarded_events
from roboto.app.git_ops import GitError
from roboto.app.i18n_assist import apply_i18n_stubs
from roboto.app.jev_guard import assess as assess_risk
from roboto.app.manager import MakeManager, manager_prompt, run_manager
from roboto.app.memory import recall_block
from roboto.app.policy import Policy
from roboto.app.provider_errors import classify_provider_error
from roboto.app.related_issues import related_issues_block
from roboto.app.repo_ci import (
    CiResult,
    Runner,
    discover_ci_commands,
    only_docs_changed,
    run_ci,
)
from roboto.app.repo_profile import (
    build_repo_profile,
    read_agents_conventions,
    sample_test_excerpt,
)
from roboto.app.reuse_metric import reuse_stat
from roboto.app.secret_scan import SecretLeakError, scan_diff
from roboto.app.self_heal import heal_missing_deps, named_deps
from roboto.app.service_provision import provision, teardown, wait_ready
from roboto.app.session_guard import may_resume, session_config_hash
from roboto.app.session_hub import SessionHub
from roboto.app.target_env import TargetEnv, read_target_env, read_target_services
from roboto.app.task_class import TaskType, classificar_task
from roboto.app.tiering import precisa_forte
from roboto.app.transient import is_transient
from roboto.app.verify import VerifyResult, arquivos_ts, secao_verify, verificar
from roboto.engines.port import CodingEngine, EngineEventKind, RunSpec
from roboto.github.app import IssueRef
from roboto.llm.decide import Decider
from roboto.llm.port import ModelGateway
from roboto.orchestrator.core import backoff_until
from roboto.orchestrator.model import Error, Run, RunState
from roboto.orchestrator.store import Store
from roboto.persona import anchor_line
from roboto.result import Err, Ok, Result

_log = logging.getLogger(__name__)
_COST_PER_MTOK = 0.4  # custo aprox. Qwen/OpenRouter ($/milhão de tokens) — medir/afinar (L)
_MAX_RUN_ATTEMPTS = 3  # teto de re-tentativas em erro transitório (B) antes de FAILED terminal
_STALL_RETRY_LIMIT = 1  # motor travado (idle-timeout): quantas re-tentativas AUTOMÁTICAS (decisão do dono)  # noqa: E501


def classificar_retry(exc: BaseException, detalhe: str, attempt: int) -> tuple[bool, str | None]:
    """Decide se um run que falhou deve RE-ENFILEIRAR (auto-retry) ou virar FAILED terminal. Puro
    (sem IO) p/ testar a política sem o daemon. Devolve ``(re_enfileira, categoria)``.

    - STALL do motor (idle-timeout → ``TimeoutError``, cujo ``str()`` é VAZIO): 1 re-tentativa só
      (``_STALL_RETRY_LIMIT``) — cobre o blip transiente do provedor; se travar de novo → terminal
      p/ o humano olhar (o dono não quer queimar token re-tentando uma task que trava sempre).
    - Erro TRANSITÓRIO de provedor (402/429/5xx/overloaded): re-tenta até ``_MAX_RUN_ATTEMPTS``.
    - Qualquer outro (bug/git/PR): terminal.
    """
    nxt = attempt + 1
    if isinstance(exc, TimeoutError):  # watchdog de inatividade (stream do ccr/OpenRouter mudo)
        return (nxt <= _STALL_RETRY_LIMIT, "stall")
    if is_transient(detalhe) and nxt < _MAX_RUN_ATTEMPTS:
        return (True, "provedor")
    return (False, None)


class GitOps(Protocol):
    async def prepare_branch(self, name: str) -> None: ...
    async def reset_to_base(self, base: str) -> None: ...  # limpa /work p/ a base (isolamento #225)
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
        self, repo: str, *, title: str, body: str, head: str, base: str = "main",
        draft: bool = False,
    ) -> Result[IssueRef, Error]: ...

    # P0b: PR nasce draft; promove a ready-for-review só quando o review aprova
    async def mark_pr_ready(self, repo: str, number: int) -> Result[None, Error]: ...

    # P0b: label `needs-human` no PR escalado (filtrável + sinal de bloqueio)
    async def add_pr_label(self, repo: str, number: int, label: str) -> Result[None, Error]: ...

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]: ...

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]: ...

    # self-heal wire (#322): reescreve o corpo da issue com a aresta `Depende de #N`
    async def update_issue(
        self, repo: str, number: int, *, title: str, body: str
    ) -> Result[None, Error]: ...

    # self-heal (#322): troca o label status:* (to-do/auto nos filhos, blocked no pai)
    async def set_issue_state_label(
        self, repo: str, number: int, label: str
    ) -> Result[None, Error]: ...

    # resumo dos checks que FALHARAM no head do PR (erro REAL da CI p/ alimentar a correção, #233)
    async def check_failures(self, repo: str, number: int) -> Result[str, Error]: ...

    # abre/fecha a issue — reverter um PR reabre a issue p/ o fleet refazer (recuperação, H)
    async def set_issue_state(
        self, repo: str, number: int, state: str
    ) -> Result[None, Error]: ...

    # estado de uma issue ("open"/"closed") — gate de dependência (J): não codar bloqueada
    async def get_issue_state(self, repo: str, number: int) -> Result[str, Error]: ...

    # labels da issue — gate de prontidão: não codar `status:blocked` (run #1046)
    async def get_issue_labels(self, repo: str, number: int) -> Result[list[str], Error]: ...

    # self-heal (fatia 2, #322): abre a issue de uma dependência NOMEADA que faltava
    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]: ...

    # self-heal: lista issues abertas (nº, título, labels) p/ dedup antes de criar
    async def list_open_issues_rich(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str, list[str]]], Error]: ...

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


_DIAG_FIX_ATTEMPTS = 2  # correções harness-driven por diagnostics do code-intel (#226)
# extensões p/ inferir a linguagem no validate_build (suporta ts/js/py/rust/csharp/dart). Ampliar
# p/ inferência pelo tipo do repo (go, etc.) é follow-up (#227).
_DIAG_EXTS = (".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".cs", ".dart")


def _diag_fix_prompt(diag: str) -> str:
    return (
        "O build AINDA tem erros (diagnostics do code-intel, no disco). Corrija EXATAMENTE estes — "
        "não chute, não reescreva o que já está certo:\n\n"
        f"{diag}\n\n"
        "Edite os arquivos e pare (não faça commit nem push)."
    )


_HOOK_FIX_ATTEMPTS = 2  # correções harness-driven quando um hook de pre-commit barra o commit
# prettier é determinístico: re-formata a CADA barrada (não só 1×). O motor pode criar arquivos
# novos entre tentativas (ex.: locales i18n) que o pre-commit `prettier --check` então rejeita;
# formatar à mão não casa com o prettier → tem de re-rodar o formatador, não devolver ao modelo.
_FMT_FIX_ATTEMPTS = 3


# porta de CI LOCAL (lint/typecheck/test) ANTES do push: bound de auto-correção. O fleet abria PR
# que o CI reprovava (lint `no-explicit-any`) porque NÃO rodava a porta do repo localmente — a saída
# vermelha chegava invisível ao operador. Agora roda a MESMA porta e devolve o vermelho ao motor.
_LOCAL_CI_FIX_ATTEMPTS = 3


# TS `noUncheckedIndexedAccess`: acessar índice de array/record vira `T | undefined`. Modelos de
# código menores escrevem o swap do algoritmo e erram ISSO (A/B T1: qwen E glm travaram no MESMO
# ponto). Assinatura do erro: TS2322 "Type 'X | undefined' is not assignable to type 'X'".
_TS_INDEX_UNDEF = re.compile(
    r"TS2322.*?Type '([^']+?) \| undefined' is not assignable to type '\1'", re.DOTALL,
)


def ts_index_safety_hint(red: str) -> str:
    """Dica DETERMINÍSTICA p/ o erro de índice sob `noUncheckedIndexedAccess` (vazio se não casa).
    O harness injeta o conhecimento que o modelo pequeno não tem — determinismo-primeiro."""
    if not _TS_INDEX_UNDEF.search(red or ""):
        return ""
    return (
        "\n\nDICA (o tsconfig tem `noUncheckedIndexedAccess: true`): acessar um índice de "
        "array/record — `arr[i]` — tem tipo `T | undefined`, NÃO `T`. É a causa do erro. Ao trocar/"
        "atribuir elementos, capture em const e trate o `undefined`. Ex. de swap seguro:\n"
        "    const a = arr[i]; const b = arr[j];\n"
        "    if (a === undefined || b === undefined) throw new Error('índice fora do range');\n"
        "    arr[i] = b; arr[j] = a;\n"
        "NÃO deixe `arr[i]` cru onde se espera `T`, e não ponha `!` só em um lado do swap."
    )


def _ci_fix_prompt(which: str, red: str) -> str:
    return (
        f"A verificação LOCAL `{which}` (A MESMA que o CI do repo aplica) REPROVOU — se eu abrir o "
        "PR assim, o CI fica vermelho. Corrija EXATAMENTE estes erros (não reescreva o que já "
        f"passa):\n\n{red}\n\n"
        "Edite os arquivos e pare (não faça commit nem push)."
        + ts_index_safety_hint(red)
    )


def _hook_fix_prompt(saida: str) -> str:
    return (
        "O COMMIT foi BLOQUEADO por um hook de pre-commit do repo (regra do projeto, INEGOCIÁVEL). "
        "Abaixo a saída do hook — faça EXATAMENTE o que ele exige (ex.: criar/atualizar o doc da "
        "rota/comportamento novo no MESMO commit, corrigir lint/i18n/tipo), sem mexer no que já "
        "está certo:\n\n"
        f"{saida}\n\n"
        "Edite os arquivos necessários e pare (NÃO faça commit nem push — o harness re-tenta)."
    )


def _should_polish_minors(
    *, aprovado: bool, close_minors: bool, n_minores: int,
    minor_done: bool, review_calls: int, max_attempts: int,
) -> bool:
    """Decide a passada BOUNDED de polimento dos MENORES (ROBOTO_CLOSE_MINORS). Puro/testável.

    SÓ poli se: review APROVOU (0 bloqueador) + toggle ligado + há menores + ainda não poliu (1 só)
    + há orçamento de tentativa (`review_calls < max_attempts`). O guard de orçamento garante que
    SEMPRE sobra uma volta p/ ACEITAR — menor NUNCA falha/bloqueia o run (é só polimento)."""
    return (
        aprovado and close_minors and n_minores > 0
        and not minor_done and review_calls < max_attempts
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
    persona: str = "",  # âncora de papel opcional (A/B atrás de flag) — ver roboto/persona.py
    decider: Decider | None = None,  # Jev degrau-2 do tier (#242): promove o que o keyword perdeu
    ci_runner: Runner | None = None,  # executor da porta de CI local (teste); None = subprocess
    make_manager: MakeManager | None = None,  # escada worker→gerente→humano (fatia 1, #322)
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
            # issues relacionadas (#N no corpo: dependência/épico): o harness LÊ e injeta o contexto
            # delas — o coder não precisa (nem deve) ir editar outras issues p/ se situar.
            related = await related_issues_block(
                run.repo, issue_body, github.get_issue, self_id=int(run.issue_id)
            )
            if related:
                contexto += "\n" + related + "\n"
    title = pr_title
    closes = f"Closes #{run.issue_id}" if run.issue_id.isdigit() else ""

    # right-sizing do motor por CLASSE de tarefa (D/F, determinístico): tarefa grande/arquitetural
    # roda no tier FORTE (ROBOTO_STRONG_MODEL, default Sonnet); pequena fica no motor barato (qwen,
    # modelo "" = default do ccr). Classificador em app/tiering.py — não é decisão de LLM.
    # degrau-1 determinístico + degrau-2 Jev (se houver decider): o Jev só PROMOVE base→forte uma
    # issue de escopo amplo que o keyword não pegou; nunca rebaixa. Sem decider = só determinístico.
    decisao_tier = await precisa_forte(pr_title, contexto or run.issue_id, decider=decider)
    # id no formato "provider,model": o ccr IGNORA o model do cliente e roteia pela config, MENOS
    # quando vem com a sintaxe de override "provider,model" — aí usa esse (validado no PoC).
    modelo_forte = os.environ.get("ROBOTO_STRONG_MODEL", "openrouter,anthropic/claude-sonnet-4.6")
    # guard (determinismo-primeiro): se o id forte não está registrado no ccr, ele responde
    # `unrecognized_model` e o run morre em ~3s SEM motivo (run #1039). Validamos ANTES e caímos no
    # base; gravamos o porquê no feed p/ o operador não ver só "failed". Fail-open se o ccr não lê.
    modelo_forte, _mf_reason = pin_or_fallback(modelo_forte, registered=registered_models())
    if _mf_reason:
        print(f"[tier] {_mf_reason}")
        if store is not None and now is not None:
            await store.append_session_event(
                run.tenant, run.id, "message", now, text="⚠️ " + _mf_reason,
            )
    # forte-UPFRONT desligado por default (#242): o grosso começa no BASE barato e o DEGRAU só sobe
    # pro forte QUANDO TRAVA — forte vira resgate RARO, não a task toda (exec #88/#93 inteiros no
    # forte = 315k/261k). Ligue ROBOTO_FORTE_UPFRONT=1 p/ começar grande direto no forte.
    _upf = os.environ.get("ROBOTO_FORTE_UPFRONT", "0").lower()
    forte_upfront = _upf not in ("0", "off", "false", "no")
    _usa_forte = forte_upfront and decisao_tier.forte and bool(modelo_forte)
    modelo_do_motor = modelo_forte if _usa_forte else ""
    # forte na FINALIZAÇÃO (#242, proativo): rascunho no BASE, mas diag/hook/correção no FORTE (a
    # ideia do dono: o base escreve, o forte FECHA a parte chata — i18n/review). Trigger = turnos
    # pós-rascunho. ROBOTO_FORTE_FINALIZE=1. Default off = reativo (só escala ao travar). A/B.
    _fin = os.environ.get("ROBOTO_FORTE_FINALIZE", "0").lower() not in ("0", "off", "false", "no")
    modelo_fin = modelo_forte if (_fin and modelo_forte) else modelo_do_motor
    print(
        f"[tier] forte={decisao_tier.forte} upfront={forte_upfront} finalize={_fin} "
        f"modelo={modelo_do_motor or '(base/qwen-coder)'} — {decisao_tier.motivo}"
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
    # teste-exemplo (G/#224): mostra o PADRÃO de teste do repo pra o motor NÃO redescobrir "como os
    # testes são feitos" (medido no feed: gastava turno explorando). Determinístico, best-effort.
    test_sample = sample_test_excerpt(workdir, hints=f"{pr_title} {contexto}")
    test_block = f"\n{test_sample}\n" if test_sample else ""
    # code-intel brief (F): injeta o catálogo de tools semânticas (puxado do PRÓPRIO MCP server) +
    # mapa do repo, pra o motor navegar/editar com code-intel em vez de grep/sed/Read (medido: ele
    # subusa). Best-effort e gated pelo mesmo flag do MCP do motor; server mudo → "".
    ci_block = ""
    if os.environ.get("ROBOTO_CODE_INTEL", "1") not in ("0", "false", "no"):
        ci_cmd = os.environ.get("ROBOTO_CODE_INTEL_CMD", "code-intel-mcp")
        brief = await asyncio.to_thread(code_intel_brief, workdir, cmd=ci_cmd)
        ci_block = f"\n{brief}\n" if brief else ""
    # #223: extrai os símbolos prováveis da issue e MANDA o motor rodar code-intel NELES antes de
    # editar (determinístico) — ataca o subuso de code-intel nos alvos (import órfão do #310).
    symbols_block = ""
    if os.environ.get("ROBOTO_CODE_INTEL", "1") not in ("0", "false", "no"):
        _directive = symbols_directive(extract_symbols(contexto))
        symbols_block = f"\n{_directive}\n" if _directive else ""
    # MAPA DO REPO (Ponytail, determinismo 1º): injeta o que JÁ existe (1 linha/dir) p/ o degrau
    # "reuse" da escada agir SEM gastar token de busca. Fail-open; ROBOTO_CODEBASE_MAP=0 desliga.
    map_block = ""
    if os.environ.get("ROBOTO_CODEBASE_MAP", "1") not in ("0", "false", "no"):
        _mapa = build_codebase_map(workdir)
        map_block = f"\n{_mapa}\n" if _mapa else ""
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
        f"{anchor_line(persona)}"
        f"Implement issue {run.issue_id} in repo {run.repo} (cwd {workdir}).{contexto}"
        f"{profile_block}{test_block}{ci_block}{symbols_block}{map_block}"
        f"{conventions_block}{memory_block}{aprendizado_block}\n"
        "MINIMAL SCOPE: deliver ONLY what the issue's Acceptance Criteria ask — nothing more. Do "
        "NOT create extra docs/files (e.g. a breakdown or epic 'update'), do NOT edit the epic nor "
        "other issues, do NOT touch unrelated code, do NOT commit lockfile/deps unless the issue "
        "requires. If you spot FUTURE work (split the epic, open sub-issues), only MENTION it at "
        "the end — do NOT create a file or issue on your own. "
        "SMALLEST COMPLETE CHANGE (lazy senior — take the 1st option that FULLY solves): "
        "(1) does it need to exist? skip feature/option/flexibility nobody asked for; (2) already "
        "in this repo (helper/component/service/pattern)? reuse it the way the surrounding code "
        "does; (3) stdlib/platform solves it? use it; (4) an installed dependency? use it — NEVER "
        "add a dep for a few lines; (5) fits in 1 readable line? one line; (6) otherwise the "
        "minimum that works. Deletion > addition. Lazy in the SOLUTION, never in the CHANGE — "
        "finish the callers/tests/fixtures you break. NEVER cut: validation at trust boundaries, "
        "error "
        "handling that prevents data loss, security, accessibility, nor anything the issue asked "
        "for. Non-trivial logic (branch/loop/parser/money/security) ships with 1 small test. "
        "A deliberate shortcut that cuts a real corner → a `shortcut: <limit>, <when to revisit>` "
        "comment on the line (the review treats that as a decision, not a bug). "
        "Follow AGENTS.md. doc-in-sync (§5): update docs ONLY if you CHANGED a rule/domain; a new "
        "endpoint/code that FOLLOWS the existing pattern needs no doc and no hunting for a doc "
        "convention (don't spend turns looking for where to document). "
        "Do ONE quick self-check: lint/typecheck + the TEST of the file(s) you changed (e.g. "
        "`vitest run <path-to-your-test>`). If it passes, great; if the environment won't let it "
        "run (infra/DB missing, slowness) or a PRE-EXISTING test fails on infra, do NOT insist — "
        "FINISH and leave the files ready (avoids blowing the turn limit). Do NOT run the whole "
        "suite (`pnpm test`). Final validation is the harness verify (types) + the PR CI (full "
        "suite with infra). "
        "Do NOT open a PR, do NOT run `git push`, `gh pr create`, nor the GitHub PR API — the "
        "FLEET does that for you (commit + push + PR). Just IMPLEMENT and leave the files ready; "
        "opening a PR here creates a DUPLICATE PR. NEVER run `git stash`, `git reset`, `git "
        "checkout -- `, "
        "nor `git clean` — it DISCARDS your work (exec #88 lost everything in a stash). To check "
        "if a failure is pre-existing, read git log/blame; don't touch the tree. "
        "TOKEN ECONOMY (F) — MANDATORY navigation rule: to DISCOVER where something is, who uses a "
        "symbol, or what breaks when you change it, ALWAYS use the code-intel tools "
        "(mcp__code-intel__find_symbol, find_references, document_symbols, blast_radius) and "
        "ripgrep for literal text — NEVER read a whole file with Read just to 'search'. Read is "
        "allowed only on the exact snippet code-intel already located. To edit a symbol "
        "(rename/move/change body), prefer the code-intel tools "
        "(rename_symbol/replace_symbol_body) over sed/regex. If you need a symbol and did NOT call "
        "code-intel first, you're doing it wrong."
    )
    state: dict[str, int] = {}  # guarda o número do PR entre tentativas
    coder: dict[str, str] = {}  # id NATIVO da sessão do coder, p/ RESUMIR na correção (= contexto)

    async def _engine_turn(prompt: str, resume: str | None, model: str | None = None) -> None:
        # um turno do motor: edita o repo, alimenta o feed ao vivo (Fatia 2) e mede o token (D10/L).
        # `model` override = degrau de escalonamento (#242): força o modelo forte se o base travar.
        modelo_efetivo = model or modelo_do_motor
        config_hash = session_config_hash(model=modelo_efetivo)
        # guard de sessão (#266): só retoma se a config bate com a que criou a sessão nativa. O
        # escalonamento (#242) troca o modelo na correção → NÃO retomar sob modelo diferente (o
        # contexto/cache da sessão do modelo base não vale pro forte).
        if resume and not may_resume(coder.get("hash"), config_hash):
            resume = None
            if store is not None and now is not None:
                await store.append_session_event(
                    run.tenant, run.id, "message", now,
                    text="♻️ sessão não retomada: a config do motor mudou (ex.: modelo "
                         "escalonado) — começo sessão nova p/ não herdar contexto incompatível.",
                )
        spec = RunSpec(
            tenant=run.tenant, repo=run.repo, workdir=workdir,
            prompt=prompt, model=modelo_efetivo, resume_session_id=resume,
        )
        started = await engine.start(spec)
        native = getattr(engine, "session_id", "") or (
            started.value if isinstance(started, Ok) else ""
        )
        if native:
            coder["native"] = native  # fixa p/ a próxima correção resumir o MESMO contexto
            coder["hash"] = config_hash  # e a config dela, p/ o guard de resume (#266)
        # cria a sessão ANTES do loop: se o motor TRAVAR (stall/idle-timeout) no meio, o `async for`
        # estoura e mesmo assim o `finally` grava o id nativo — p/ "responder depois do timeout"
        # retomar a MESMA sessão com contexto (start_session resume o native_session_id), não do 0.
        session = None
        if store is not None and now is not None:
            session = await store.create_session(
                run.tenant, run.id, engine.engine, now, config_hash=config_hash
            )
        tin = tout = 0
        try:
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
        finally:
            # o id nativo só é conhecido DURANTE o events() (chega no 1º AssistantMessage); re-lê e
            # grava — inclusive se o loop estourou por stall — p/ o resume humano achar a sessão.
            nid = getattr(engine, "session_id", "") or native
            if nid:
                coder["native"] = nid
                coder["hash"] = config_hash
                if session is not None and store is not None and now is not None:
                    await store.set_native_session(session.id, nid, now)
        if store is not None and now is not None:
            await store.record_llm_call(
                tenant=run.tenant, run_id=run.id, provider="openrouter",
                model="qwen/qwen3-coder", tier="frontier", tokens_in=tin, tokens_out=tout,
                cost_usd=(tin + tout) / 1_000_000 * _COST_PER_MTOK, now=now,
            )

    async def implement(feedback: list[str]) -> PullRequest:
        prompt = base_prompt
        baseline_red = ""
        if feedback:
            prompt += "\nCorrija os pontos do review:\n- " + "\n- ".join(feedback)
        else:
            # isolamento por run (#225): limpa o /work p/ a base ANTES do motor — senão herda a
            # árvore do run anterior no /work compartilhado (PR contaminado, ex.: #250). Só na 1ª
            # tentativa: correções (feedback) editam SOBRE o trabalho já feito, não resetam.
            await git.reset_to_base(base)
            # guard de baseline (#247): o repo-alvo pode ter o pre-commit VERMELHO por DÍVIDA
            # pré-existente (ex.: 555 chaves i18n faltando repo-wide) → barra QUALQUER commit, não é
            # a mudança do fleet. Prova na base limpa p/ não culpar o modelo. Best-effort.
            try:
                baseline_red = await git.precommit_baseline()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — probe best-effort, nunca derruba o ciclo
                baseline_red = ""
            if baseline_red and store is not None and now is not None:
                await store.append_session_event(
                    run.tenant, run.id, "message", now,
                    text="⚠️ pre-commit do repo-alvo JÁ está vermelho na BASE (dívida "
                         "pré-existente) — vai barrar qualquer commit; não é a sua mudança.",
                )
        # correção RESUMINDO a sessão do coder: 1ª tentativa é sessão nova; correções resumem.
        # rascunho (sem feedback) no base; correção (feedback) no modelo_fin (forte se FINALIZE).
        await _engine_turn(
            prompt, coder.get("native") if feedback else None,
            model=modelo_fin if feedback else None,
        )
        await git.prepare_branch(branch)
        # diagnostics HARNESS-DRIVEN (#226): o motor subusa o code-intel p/ entender erro de build
        # (medido #46: tsc no braço). O harness roda validate_build e injeta os erros ESTRUTURADOS
        # p/ o motor corrigir com precisão. Gated + BEST-EFFORT (nunca derruba o ciclo) + bounded.
        if os.environ.get("ROBOTO_CODE_INTEL", "1") not in ("0", "false", "no"):
            try:
                # árvore de trabalho (não o diff commitado, vazio pré-commit — bug #226)
                changed = await git.working_changes()  # type: ignore[attr-defined]
                amostra = next((f for f in changed if f.endswith(_DIAG_EXTS)), "")
                diag = await asyncio.to_thread(code_intel_diagnostics, workdir, amostra)
                dtries = 0
                while diag and dtries < _DIAG_FIX_ATTEMPTS:
                    dtries += 1
                    if store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text=f"↻ diagnostics (code-intel): corrigindo build (try {dtries}).",
                        )
                    await _engine_turn(
                        _diag_fix_prompt(diag), coder.get("native"), model=modelo_fin
                    )
                    diag = await asyncio.to_thread(code_intel_diagnostics, workdir, amostra)
            except Exception:  # noqa: BLE001 — diagnostics é best-effort; não derruba o ciclo
                pass
        # auto-format (F/B, determinismo): o motor costuma esquecer de formatar e o pre-commit hook
        # (prettier --check) barra o commit. O harness formata os arquivos alterados pré-commit.
        formatados = await autoformat(workdir)
        if formatados and store is not None and now is not None:
            await store.append_session_event(
                run.tenant, run.id, "message", now,
                text=f"🎨 auto-format: {len(formatados)} arquivo(s) formatado(s) antes do commit.",
            )
        # commit resiliente ao pre-commit hook: a saída do hook é a fonte da verdade (determinismo).
        # - formatação (#228, prettier --check): o harness formata e re-tenta (não gasta o motor).
        # - qualquer OUTRO hook (doc-sync, lint, i18n, tipo): devolve a saída ao motor p/ corrigir e
        #   re-tenta — bounded. Era o buraco que matava motor bom (#57: doc-sync exige doc da rota
        #   nova; o motor tinha implementado tudo, só faltava o doc).
        _msg = title if not feedback else f"{title} (correção)"
        fmt_tries = hook_tries = i18n_tries = 0
        escalado = False  # degrau (#242): 1 turno no modelo forte se o base travar
        while True:
            try:
                await git.commit_all(_msg)
                break
            except GitError as _exc:
                low = str(_exc).lower()
                if ("prettier" in low or "code style" in low) and fmt_tries < _FMT_FIX_ATTEMPTS:
                    fmt_tries += 1
                    refmt = await autoformat(workdir)
                    if refmt and store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text=f"🎨 commit barrado por formatação → reformatei {len(refmt)}.",
                        )
                    continue
                # i18n DETERMINÍSTICO (#247): o check:i18n ENTREGA a chave exata faltando — o
                # harness a stuba nos locales (imune ao drift do modelo, que inventa camelCase).
                # Antes do modelo (determinismo 1º). 1×: se não resolver, cai no motor/forte.
                if "i18n" in low and i18n_tries < 1:
                    i18n_tries += 1
                    stubbed = apply_i18n_stubs(workdir, str(_exc))
                    if stubbed and store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text=f"🌐 i18n: stub determinístico de {len(stubbed)} chave(s) "
                                 "(revise as traduções no PR).",
                        )
                    if stubbed:
                        await autoformat(workdir)
                        continue
                if hook_tries < _HOOK_FIX_ATTEMPTS:
                    hook_tries += 1
                    if store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text=f"↻ commit barrado por hook → motor corrige (try {hook_tries}).",
                        )
                    await _engine_turn(
                        _hook_fix_prompt(str(_exc)), coder.get("native"), model=modelo_fin
                    )
                    # determinismo: o motor pode ter criado/editado arquivos no turno acima (ex.:
                    # locales i18n) → re-formata com o prettier ANTES do próximo commit; senão o
                    # `--check` barra e a correção à mão do modelo nunca casa (buraco do #245).
                    await autoformat(workdir)
                    continue
                # DEGRAU DE ESCALONAMENTO (#242): o modelo BASE esgotou o hook → antes de desistir,
                # 1 turno com o MODELO FORTE (Sonnet) corrigindo o hook. O forte fecha
                # i18n/doc-sync que o qwen não fecha (medido: Sonnet corrige limpo). Bounded (1×).
                if modelo_forte and modelo_do_motor != modelo_forte and not escalado:
                    escalado = True
                    if store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text="⚡ hook não cedeu no modelo base → escalando p/ o MODELO FORTE.",
                        )
                    await _engine_turn(
                        _hook_fix_prompt(str(_exc)), coder.get("native"), model=modelo_forte
                    )
                    await autoformat(workdir)
                    continue
                # hook NÃO-prettier não cedeu nem no forte (i18n/doc-sync não são mecânicos). Escala
                # LIMPO p/ humano em vez de FAILED seco com GitError cru (exec #80: morreu no i18n).
                if store is not None and now is not None:
                    extra = (
                        " NOTA: este hook JÁ estava vermelho na BASE (dívida pré-existente do "
                        "repo) — precisa de LIMPEZA do repo, não é a sua mudança."
                        if baseline_red else ""
                    )
                    await store.append_session_event(
                        run.tenant, run.id, "message", now,
                        text=(f"🚩 hook de pre-commit não passou após {_HOOK_FIX_ATTEMPTS} "
                              f"tentativas (não é mecânico). Precisa de humano.{extra}"),
                    )
                    if run.origin_chat_id:
                        await store.enqueue_effect(
                            run.tenant, run.id, "telegram_notify",
                            {"chat_id": run.origin_chat_id,
                             "text": f"🚩 #{run.issue_id}: hook de pre-commit (i18n/doc-sync) "
                                     f"não passou após {_HOOK_FIX_ATTEMPTS} tentativas — humano."},
                            f"hookfail:{run.id}", now,
                        )
                raise  # esgotou as tentativas → propaga (FAILED), agora com sinal claro p/ humano
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
            await _engine_turn(_secret_fix_prompt(leak), coder.get("native"), model=modelo_fin)
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
        diff_atual = await git.diff(base)
        if not diff_atual.strip():
            raise RuntimeError("motor não editou nada (diff vazio vs base) — nada a revisar")
        # MÉTRICA DE REUSO (Ponytail): quantas chamadas do código novo reusam símbolos já no repo —
        # KPI de "reuse-first" por run. Best-effort; ROBOTO_REUSE_METRIC=0 desliga.
        if (
            store is not None and now is not None
            and os.environ.get("ROBOTO_REUSE_METRIC", "1") not in ("0", "false", "no")
        ):
            rs = reuse_stat(diff_atual, workdir)
            if rs.total:
                await store.append_session_event(
                    run.tenant, run.id, "message", now,
                    text=f"♻️ reuso: {rs.reused}/{rs.total} chamadas do código novo reusam símbolos "
                    f"já existentes ({round(rs.ratio * 100)}%).",
                )
        # PORTA DE CI LOCAL (determinismo 1º): roda a MESMA porta do CI (lint/typecheck/test) ANTES
        # do push. Vermelho de CÓDIGO volta ao motor (bounded; última no forte) + re-commit;
        # verde → segue. Vermelho de INFRA (DB fora/deps) degrada p/ surfado (não trava, CI é juiz).
        # Fecha o buraco: o fleet não abre mais PR que o CI vai reprovar, e o vermelho fica VISÍVEL.
        if os.environ.get("ROBOTO_LOCAL_CI", "1") not in ("0", "off", "false", "no"):
            ci_cmds = discover_ci_commands(
                workdir, override=os.environ.get("ROBOTO_LOCAL_CI_CMDS", "")
            )
            # mudança SÓ-DOC não precisa de build/test (nem de subir serviços): poupa o turbo (CPU)
            # e o provisionamento. O CI do GitHub ainda roda tudo; aqui é só o gate local.
            if ci_cmds and only_docs_changed(changed_files_from_diff(diff_atual)):
                pulados = [n for n, _ in ci_cmds if n in ("test", "build")]
                ci_cmds = [(n, c) for n, c in ci_cmds if n not in ("test", "build")]
                if pulados and store is not None and now is not None:
                    await store.append_session_event(
                        run.tenant, run.id, "message", now,
                        text=f"📄 mudança só-doc: pulo {'/'.join(pulados)} (sem subir serviços; o "
                        "CI do GitHub valida).",
                    )
            if ci_cmds:
                # RESILIÊNCIA: lê o CI do alvo (env/services/setup) p/ SUBIR o ambiente de teste e
                # rodar o `test` de verdade (não chutar "infra"). ROBOTO_PREPARE_ENV=0 desliga.
                tenv = (
                    read_target_env(workdir)
                    if os.environ.get("ROBOTO_PREPARE_ENV", "1") not in ("0", "off", "false", "no")
                    else TargetEnv()
                )

                def _run_ci() -> CiResult:  # closure: fixa setup/env/services do alvo nas re-rodas
                    return run_ci(
                        workdir, ci_cmds, setup=tenv.setup, env=tenv.env,
                        services=tenv.services, runner=ci_runner,
                    )

                # PROVISIONA os serviços do CI do alvo (postgres/redis…) EFÊMEROS, só se a task
                # roda teste. Sobem na REDE do fleet (localhost compartilhado) e CAEM no finally.
                # ROBOTO_PROVISION_SERVICES=0 desliga (usa o que já estiver no ambiente).
                _svcs = (
                    read_target_services(workdir)
                    if os.environ.get("ROBOTO_PROVISION_SERVICES", "1")
                    not in ("0", "off", "false", "no")
                    and any(n == "test" for n, _ in ci_cmds)
                    else []
                )
                _provisionado = False
                if _svcs:
                    _nomes = await asyncio.to_thread(
                        provision, _svcs, run_id=run.id, self_container=socket.gethostname(),
                    )
                    _provisionado = bool(_nomes)
                    if _provisionado and store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text=f"🧪 subi {len(_nomes)} serviço(s) efêmero(s) p/ o teste "
                            f"({', '.join(s.name for s in _svcs)}); derrubo no fim.",
                        )
                        # espera as portas ACEITAREM conexão (postgres só binda 5432 após iniciar) —
                        # melhor que sleep fixo; era por isso que o teste batia antes de pronto.
                        _pronto = await asyncio.to_thread(wait_ready, _svcs)
                        if not _pronto and store is not None and now is not None:
                            await store.append_session_event(
                                run.tenant, run.id, "message", now,
                                text="⏳ serviços efêmeros demoraram a aceitar conexão; "
                                "o setup/test ainda tenta.",
                            )
                try:
                    ci = await asyncio.to_thread(_run_ci)
                    ci_tries = 0
                    while ci.fixable and ci_tries < _LOCAL_CI_FIX_ATTEMPTS:
                        ci_tries += 1
                        model_ci = (
                            modelo_forte
                            if (modelo_forte and ci_tries >= _LOCAL_CI_FIX_ATTEMPTS)
                            else modelo_fin
                        )
                        if store is not None and now is not None:
                            await store.append_session_event(
                                run.tenant, run.id, "message", now,
                                text=f"🔴 CI local `{ci.which}` reprovou → corrige ({ci_tries}).",
                            )
                        await _engine_turn(
                            _ci_fix_prompt(ci.which, ci.red), coder.get("native"), model=model_ci
                        )
                        await autoformat(workdir)
                        try:
                            await git.commit_all(f"{title} (fix CI {ci.which})")
                        except GitError:
                            pass  # hooks já passaram no 1º commit; re-commit é best-effort
                        ci = await asyncio.to_thread(_run_ci)
                    if ci.infra:
                        if store is not None and now is not None:
                            # HONESTA: diz se TENTAMOS subir o ambiente e qual serviço faltou,
                            # em vez do antigo "infra, não a sua mudança" cego.
                            if ci.prepared:
                                svc = (
                                    f" (faltou subir: {', '.join(ci.services)})"
                                    if ci.services else ""
                                )
                                detalhe = (
                                    f"tentei subir o ambiente (setup do repo) e `{ci.which}` "
                                    f"seguiu indisponível por infra{svc}"
                                )
                            else:
                                detalhe = (
                                    f"`{ci.which}` indisponível localmente e sem setup no repo p/ "
                                    "subir o ambiente de teste"
                                )
                            await store.append_session_event(
                                run.tenant, run.id, "message", now,
                                text=f"⚠️ CI local: {detalhe} — o CI do GitHub é OBRIGATÓRIO antes "
                                     "do merge.",
                            )
                    elif not ci.passed:
                        # ESCADA worker→gerente→humano (fatia 1, épico #322): o worker esgotou as
                        # tentativas; ANTES do humano, um GERENTE (motor FORTE, agêntico) pega o
                        # estado travado e tenta. Re-verifica o gate; só escala pro humano se ele
                        # também falhar. Determinístico: o harness decide QUANDO; o gerente resolve.
                        if make_manager is not None and ci.fixable:
                            if store is not None and now is not None:
                                await store.append_session_event(
                                    run.tenant, run.id, "message", now,
                                    text=f"🧑‍💼 worker empacou no `{ci.which}` — gerente (forte) "
                                         "assumindo…",
                                )
                            await run_manager(
                                make_manager, tenant=run.tenant, repo=run.repo, workdir=workdir,
                                prompt=manager_prompt(ci.which, ci.red, pr_title, contexto),
                            )
                            await autoformat(workdir)
                            try:
                                await git.commit_all(f"{title} (gerente)")
                            except GitError:
                                pass
                            ci = await asyncio.to_thread(_run_ci)  # re-verifica após o gerente
                            if ci.passed and store is not None and now is not None:
                                await store.append_session_event(
                                    run.tenant, run.id, "message", now,
                                    text=f"✅ gerente resolveu o `{ci.which}` — CI local verde, "
                                         "sem humano (escada worker→gerente).",
                                )
                        if not ci.passed:  # worker E gerente falharam → agora sim, humano
                            if store is not None and now is not None:
                                await store.append_session_event(
                                    run.tenant, run.id, "message", now,
                                    text=f"🚩 CI local `{ci.which}` segue vermelho (worker + "
                                         "gerente) — humano (PR não sai).",
                                )
                                if run.origin_chat_id:
                                    await store.enqueue_effect(
                                        run.tenant, run.id, "telegram_notify",
                                        {"chat_id": run.origin_chat_id,
                                         "text": f"🚩 #{run.issue_id}: CI local ({ci.which}) "
                                                 "vermelho após worker + gerente — precisa de "
                                                 "humano."},
                                        f"localci:{run.id}", now,
                                    )
                            raise RuntimeError(
                                f"CI local ({ci.which}) segue vermelho após worker + gerente — "
                                "escala p/ humano (não abre PR vermelho)"
                            )
                    elif ci.prepared and store is not None and now is not None:
                        # resiliência: subimos o ambiente e o teste passou DE VERDADE (não pulado)
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text="🔧 subi o ambiente (setup do repo) e o `test` passou ✅ — "
                                 "validado de verdade, não pulado.",
                        )
                    elif ci_tries and store is not None and now is not None:
                        await store.append_session_event(
                            run.tenant, run.id, "message", now,
                            text=f"✅ CI local verde após {ci_tries} correção(ões) — PR verde.",
                        )
                finally:
                    if _provisionado:
                        _n = await asyncio.to_thread(teardown, run.id)
                        if _n and store is not None and now is not None:
                            await store.append_session_event(
                                run.tenant, run.id, "message", now,
                                text=f"🧹 derrubei {_n} serviço(s) efêmero(s) do teste.",
                            )
        # #281: o PUSH tem de incluir TUDO que o CI local validou (o worktree). Motor deixou arquivo
        # fora do commit (ex.: import órfão do #310) → CI local verde, GitHub vermelho.
        # commit_all faz `git add -A` e é no-op se a árvore está limpa.
        try:
            await git.commit_all(f"{title} (worktree validado localmente, #281)")
        except GitError:
            pass  # hook já passou antes; re-commit defensivo é best-effort
        await git.push(branch)
        if "pr" not in state:
            # idempotência contra PR vivo: reaproveita o PR aberto do branch, se houver
            existing = await github.find_open_pr(run.repo, branch)
            if isinstance(existing, Ok) and existing.value is not None:
                state["pr"] = existing.value
            else:
                # P0b: PR NASCE DRAFT (não-mergeável). Só vira ready-for-review quando o review
                # APROVA (process_pr_run_tick). Um run escalado/não-aprovado nunca deixa um PR que o
                # humano mergeia num clique sem ver o 🚩 (furo do run-1047/#399).
                opened = await github.open_pr(
                    run.repo, title=title, body=await build_pr_body(), head=branch, base=base,
                    draft=True,
                )
                # #144: open_pr falho NÃO vira PR nº 0 silencioso — propaga e FALHA o run (senão o
                # review rodava sobre diff vazio). A msg do adapter traz o motivo real (422).
                if isinstance(opened, Err):
                    raise RuntimeError(f"open_pr falhou: {opened.error}")
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
        # #3 visibilidade: surfa o VEREDITO do review no feed a cada tentativa. Sem isto o console
        # só mostrava o lado do implement (CI local) — o operador não via O QUÊ o review reprovou
        # entre as voltas, só o agregado final no encerramento. Agora cada review deixa rastro.
        if store is not None and now is not None:
            if aprovado:
                texto_review = "🔍 Review: aprovado ✅ — sem bloqueadores."
            else:
                detalhe = "\n".join(f"• {problema}" for problema in issues) or "• (sem detalhe)"
                texto_review = f"🔍 Review: reprovou 🔴 ({len(issues)} ponto(s)):\n{detalhe}"
            await store.append_session_event(
                run.tenant, run.id, "message", now, text=texto_review,
            )
        # second brain (Fatia 1): registra o FATO do review (veredito + títulos dos findings) —
        # greppável; alimenta o refino/impl de relacionadas. Dedup por ref (review vigente).
        if store is not None and now is not None:
            titulos = "; ".join(f.titulo for f in findings[:5]) or "sem apontamentos"
            veredito = "aprovado" if aprovado else "reprovado"
            await store.remember(
                run.tenant,
                f"Review PR #{pr.number} (issue #{run.issue_id}): {veredito}. {titulos}"[:400],
                kind="fato", ref=f"#{run.issue_id}", now=now, unique_by_ref=True,
            )
        # fecha MENORES (toggle ROBOTO_CLOSE_MINORS): review aprovou (0 bloqueador) mas sobraram
        # ressalvas MENORES → UMA passada de polimento BOUNDED, SÓ se há orçamento de tentativa
        # (senão aceita). Menor NUNCA bloqueia/falha o run; os findings vão injetados na correção.
        menores = [
            f"[{f.severidade}] {f.titulo} ({f.arquivo}:{f.linha}) — {f.recomendacao}"
            for f in findings
            if f.severidade == "menor"
        ]
        state["review_calls"] = state.get("review_calls", 0) + 1
        close_minors = os.environ.get("ROBOTO_CLOSE_MINORS", "0") in ("1", "true", "yes")
        if _should_polish_minors(
            aprovado=aprovado, close_minors=close_minors, n_minores=len(menores),
            minor_done=bool(state.get("minor_done")), review_calls=state["review_calls"],
            max_attempts=max_attempts,
        ):
            state["minor_done"] = 1  # uma passada só (conservador); depois aceita o que sobrar
            if store is not None and now is not None:
                await store.append_session_event(
                    run.tenant, run.id, "message", now,
                    text=f"🧹 Fechando {len(menores)} menor(es) não-bloqueante(s) — passada de "
                    "polimento (depois aceita o que sobrar; menor não bloqueia).",
                )
            return ReviewVerdict(approved=False, issues=menores, summary=body[:200])
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
    persona: str = "",  # âncora de papel opcional (A/B atrás de flag) — ver roboto/persona.py
    decider: Decider | None = None,  # Jev degrau-2 do tier (#242); None = só determinístico
    hub: SessionHub | None = None,  # gate por ação (#271): sessão viva p/ o callback aguardar
    approval_policy: Policy | None = None,  # policy de 2 eixos; None = sem gate (fluxo autônomo)
    make_manager: MakeManager | None = None,  # escada worker→gerente→humano (fatia 1, #322)
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
            # SELF-HEAL (fatia 2, #322): dependências NOMEADAS (não-`#N`) que não viraram issue →
            # abre esqueleto rastreado + comenta no pai, destravando a cadeia (ex.: a #286 dependia
            # de "T1/T2" que o parser de `#N` não via). ROBOTO_SELF_HEAL_DEPS liga (impacta: cria
            # issue). Esqueleto nasce sem DoR → o próprio gate abaixo não deixa codar sem refino.
            if (
                os.environ.get("ROBOTO_SELF_HEAL_DEPS", "").lower() in ("1", "true", "yes", "on")
                and named_deps(body)
            ):
                _lst = await github.list_open_issues_rich(run.repo, limit=60)
                _titles = [t for _, t, _ in _lst.value] if isinstance(_lst, Ok) else []

                async def _create(repo: str, ttl: str, bdy: str) -> int | None:
                    r = await github.create_issue(repo, ttl, bdy)
                    return r.value.number if isinstance(r, Ok) else None

                async def _comment(repo: str, n: int, txt: str) -> None:
                    await github.comment_pr(repo, n, txt)

                async def _add_label(repo: str, n: int, label: str) -> None:
                    await github.set_issue_state_label(repo, n, label)

                async def _update_body(repo: str, n: int, new_body: str) -> None:
                    cur = await github.get_issue(repo, n)  # relê o título (update_issue o exige)
                    if isinstance(cur, Ok):
                        await github.update_issue(repo, n, title=cur.value[0], body=new_body)

                _criados = await heal_missing_deps(
                    repo=run.repo, parent=int(run.issue_id), body=body, existing_titles=_titles,
                    create_issue=_create, comment=_comment,
                    add_label=_add_label, update_body=_update_body,
                )
                if _criados:
                    await store.append_session_event(
                        run.tenant, run.id, "message", moment,
                        text=f"⚙️ self-heal: abri {len(_criados)} dependência(s) faltante(s) "
                             f"({', '.join(f'#{n}' for n in _criados)}) — gravei a aresta "
                             "`Depende de #N` no corpo e re-bloqueei (status:blocked) até refino.",
                    )
            # gate de PRONTIDÃO por LABEL (#1046): `status:blocked` é o veredito humano/refino de
            # que a issue NÃO está pronta — captura bloqueio que o parser de `#N` não vê (ex.: a
            # #286 dependia de T1/T2 que nem eram issue). Não coda; espera destravar (label sai).
            labs = await github.get_issue_labels(run.repo, int(run.issue_id))
            if isinstance(labs, Ok) and (bl := blocking_labels(labs.value)):
                await github.comment_pr(
                    run.repo, int(run.issue_id),
                    f"Issue marcada não-pronta ({', '.join(bl)}) — não implemento até destravar.",
                )
                await store.set_state(run.id, RunState.WAITING, moment)
                return
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
            # right-sizing NÃO bloqueia o impl (revertido): contar critério é proxy ruim de
            # épico — uma feature coesa pode ter 9 critérios (#297). O sinal é advisory no REFINO
            # (loops, via `assess_epic` + Jev); aqui o impl confia que o refino já right-sizou.
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
    # gate por ação (#271, opt-in): com hub+policy, cada ação do motor passa pelo gate humano
    # (policy → auto/ask/off). Default OFF → fluxo autônomo (bypassPermissions) intacto.
    set_approval = getattr(engine, "set_approval", None)
    gate_hub = hub if (approval_policy is not None and callable(set_approval)) else None
    if gate_hub is not None and approval_policy is not None and set_approval is not None:
        live = gate_hub.open(run.id)
        set_approval(
            make_policy_callback(
                store=store, live=live, tenant=tenant, execution_id=run.id,
                policy=approval_policy, now=now,
            )
        )
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
            persona=persona,
            decider=decider,
            make_manager=make_manager,
        )
    except Exception as exc:  # noqa: BLE001 — motor travado (watchdog) / git / PR: tira de RUNNING
        # OBSERVABILIDADE: alguns erros (ex.: engine/CLI) têm str() vazio → a msg virava "execução
        # falhou:" sem nada (inútil p/ diagnóstico). Agora caímos no TIPO do erro + logamos o
        # traceback no daemon (antes era engolido no append_session_event).
        detalhe = str(exc).strip() or type(exc).__name__
        _log.exception("process_pr_run_tick run #%s falhou: %s", run.id, detalhe)
        # Re-enfileira (auto-retry) OU vira FAILED terminal conforme a política (classificar_retry):
        # motor travado (idle-timeout) → 1x; transitório de provedor (402/429/5xx) → até o teto. O
        # daemon retoma SOZINHO (o humano não re-dispara). `str(TimeoutError())` é vazio, por isso a
        # política casa no TIPO do erro, não na mensagem (bug do #1042: stall virava retry mudo).
        nxt = run.attempt + 1
        re_enfileira, categoria = classificar_retry(exc, detalhe, run.attempt)
        if re_enfileira:
            await store.requeue_run_with_backoff(run.id, nxt, backoff_until(nxt, moment), moment)
            txt = (
                f"⏳ motor travado (stream mudo) — re-enfileirado 1x (tentativa {nxt}); se travar "
                f"de novo vira terminal. Retoma sozinho, sem ação sua."
                if categoria == "stall"
                else f"⏳ erro transitório (provedor) — re-enfileirado (tentativa {nxt}) com "
                f"backoff; retoma sozinho quando passar: {detalhe}"
            )
            await store.append_session_event(run.tenant, run.id, "message", moment, text=txt)
            return
        await store.set_state(run.id, RunState.FAILED, moment)
        op = classify_provider_error(str(exc))  # billing/cota do provider → msg clara, não bug
        await store.append_session_event(
            run.tenant, run.id, "message", moment,
            text=op or f"⚠️ execução falhou: {detalhe}",
        )
        return
    finally:
        if gate_hub is not None and set_approval is not None:
            set_approval(None)  # limpa o gate do motor compartilhado após o run (#271)
            gate_hub.close(run.id)
    await store.set_state(
        run.id, RunState.VERIFYING if result.approved else RunState.FAILED, moment
    )
    # P0b: o PR nasce DRAFT — aqui decidimos se vira mergeável. APROVADO → promove a ready (humano
    # mergeia). ESCALADO → fica draft + label `needs-human` (GitHub não deixa mergear PR draft).
    _pr = result.pr
    if _pr is not None and _pr.number:
        if result.approved:
            _r = await github.mark_pr_ready(run.repo, _pr.number)
            if isinstance(_r, Err):
                await store.append_session_event(
                    run.tenant, run.id, "message", moment,
                    text=f"⚠️ PR #{_pr.number} aprovado mas não consegui tirar do draft "
                         f"({_r.error}) — fica draft; marque 'Ready for review' no GitHub.",
                )
        else:
            await github.add_pr_label(run.repo, _pr.number, "needs-human")
    if not result.approved:
        # terminal VISÍVEL no console: sem isto, o feed termina na última msg do implement (ex.: o
        # aviso benigno de CI local INFRA) e o run vira `failed` SEM explicação — parece que o CI
        # local falhou. Surface o motivo real: o review não aprovou após N tentativas + pendências.
        pendencias = "; ".join(result.issues[:5]) if result.issues else "sem pendências registradas"
        await store.append_session_event(
            run.tenant, run.id, "message", moment,
            text=f"🚩 Encerrado sem aprovação após {result.attempts} tentativa(s) de review — "
                 f"precisa de humano. Pendências do review: {pendencias}",
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


# bound de auto-correção por PR (#233). VALIDADO pela literatura: o ganho da auto-correção se
# concentra nas ~2 primeiras rodadas (76–95%); além de ~4 cai a zero (falta de CONTEXTO, não de
# tentativas). "Três é o número mágico" (arXiv 2607.05197, 2604.10508). Alinha com max_attempts=3.
_CORRECT_MAX_ATTEMPTS = 3
# a partir desta rodada de correção (prior inclui a atual), o coder sobe pro modelo forte (#242
# Fatia 3): 1ª no base barato; não convergiu → forte, antes de bater o bound e escalar p/ humano.
_CORRECT_ESCALATE_AT = 2


def _correct_prompt(repo: str, pr_number: int, workdir: str, issues: list[str]) -> str:
    return (
        f"Corrija os APONTAMENTOS do review no PR #{pr_number} do repo {repo} (cwd {workdir}). "
        "Você está NA branch do PR, com o código já implementado — faça SÓ os ajustes abaixo, sem "
        "reimplementar nem sair do escopo. Self-check rápido (lint/typecheck + teste SÓ do que "
        "mexeu, não a suíte); se o ambiente não deixar rodar (infra/DB), NÃO insista — conclua. "
        "NUNCA rode `git stash`, `git reset`, `git checkout -- ` nem `git clean` — DESCARTA o seu "
        "trabalho (exec #88 perdeu tudo num stash); o FLEET cuida do git. "
        "Pontos do review:\n- " + "\n- ".join(issues)
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

    async def _review_now(previas: list[str] | None = None) -> ReviewVerdict:
        diff = await github.get_pr_diff(run.repo, pr_number)
        pr = PullRequest(
            number=pr_number,
            author=str(engine.engine),
            title=f"PR #{pr_number}",
            diff=diff.value if isinstance(diff, Ok) else "",
        )
        # anchora o re-review nos pontos ANTERIORES (#151/convergência): o juiz VERIFICA se cada um
        # foi resolvido, em vez de re-revisar do zero e inventar bloqueadores novos a cada rodada
        # (era por que o loop review→correção→re-review nunca fechava — #254).
        res = await revisar_pr(pr, gateway, reviewer=reviewer, contexto_previo=previas)
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

        # RE-CHECK de CI (poll-correct-ci): o poll disparou SÓ porque a CI virou vermelha num commit
        # JÁ avaliado. Aqui NÃO re-revisamos o doc — senão o juiz acha um bloqueador novo a cada
        # rodada, corrige, empurra (novo sha) e vira churn. Trata-se SÓ da CI (via triagem abaixo):
        # força o veredito aprovado p/ que apenas a CI decida o que fazer.
        ci_recheck = run.idempotency_key.startswith("poll-correct-ci")
        verdict = ReviewVerdict(approved=True, issues=[]) if ci_recheck else await _review_now()
        # CI VERMELHA é AUTORITATIVA (#233): lê o erro REAL (tsc/lint) e alimenta a correção — o
        # juiz lê só o diff e pode não ver o erro de tipo (deixou o #252 vermelho e "aprovado").
        cf = await github.check_failures(run.repo, pr_number)
        # RESILIÊNCIA: um ERRO da API de checks (403 sem `Checks:read`, timeout) NÃO é "CI verde".
        # Antes `Err → ""` fazia o run afirmar "CI verde" e seguir — um erro de permissão disfarçado
        # de aprovação (achado no #318). Agora separamos "indisponível" de "sem falhas".
        ci_unknown = isinstance(cf, Err)
        ci_errs = cf.value if isinstance(cf, Ok) else ""
        ci_triada = False  # True quando a triagem removeu um vermelho ALHEIO (≠ CI verde)
        if ci_unknown:
            await store.append_session_event(
                run.tenant, run.id, "message", moment,
                text="⚠️ status de CI INDISPONÍVEL (não consegui ler os check-runs — confira a "
                     "permissão `Checks: read` do token). NÃO afirmo CI verde.",
            )

        # TRIAGEM de CI (o AGENTE faz o levantamento; a POLÍTICA decide): nem toda CI vermelha é
        # NOSSA. Vuln de dep pré-existente, erro de config de pipeline ou infra NÃO devem forçar
        # ESTE PR a consertar (flail/out-of-scope). Se não for do diff deste PR → abre issue
        # dedicada (dedup) ou escala, e remove o vermelho alheio do feedback. ROBOTO_CI_TRIAGE=0.
        if ci_errs and os.environ.get("ROBOTO_CI_TRIAGE", "1") not in ("0", "off", "false", "no"):
            diff_pr = await github.get_pr_diff(run.repo, pr_number)
            diff_txt = diff_pr.value if isinstance(diff_pr, Ok) else ""
            triage = await triar_ci(ci_errs, changed_files_from_diff(diff_txt), diff_txt, gateway)
            if acao_ci(triage) != ACAO_CORRIGIR:
                ci_errs = ""  # não é nosso → não realimenta a correção com o vermelho alheio
                ci_triada = True  # neutralizamos um vermelho ALHEIO (não é "CI verde")
                if acao_ci(triage) == ACAO_ABRIR_ISSUE and triage.titulo:
                    aberta = await store.enqueue_effect(
                        run.tenant, run.id, "create_issue",
                        {"repo": run.repo, "title": f"[CI] {triage.titulo}",
                         "body": ci_issue_body(triage, run.repo, pr_number)},
                        f"ci-task:{run.repo}:{triage.dedup or triage.titulo}", moment,
                    )
                    texto = (
                        f"🔎 Triagem de CI: `{triage.categoria}` NÃO causado por este PR → "
                        + ("abri issue de follow-up" if aberta else "issue já aberta (dedup)")
                        + ". O vermelho é pré-existente; este PR não precisa consertar."
                    )
                else:
                    texto = (
                        f"🔎 Triagem de CI: `{triage.categoria}` (conf {triage.confianca}) não é "
                        "código deste PR → escala p/ humano (retry/ignorar); o PR não conserta."
                    )
                await store.append_session_event(
                    run.tenant, run.id, "message", moment, text=texto
                )

        if verdict.approved and not ci_errs:
            # honesto: "CI verde" só se REALMENTE leu e não havia falha; se a triagem removeu um
            # vermelho ALHEIO, diz isso; se não leu os checks, diz indisponível.
            ci_txt = (
                "CI alheia triada (issue aberta)" if ci_triada
                else "CI indisponível (não lida)" if ci_unknown
                else "CI verde"
            )
            await github.comment_pr(
                run.repo, pr_number,
                f"✅ Correção: nada a ajustar — review aprovado ({ci_txt}).",
            )
            await store.append_session_event(
                run.tenant, run.id, "message", moment,
                text=f"✅ review aprovado + {ci_txt} — nada a corrigir",
            )
            await store.set_state(run.id, RunState.DONE, moment)
            return

        # bound por PR: esgotou as tentativas e o PR SEGUE reprovado (CI vermelha OU review com
        # bloqueador) → para e escala p/ humano. Antes só escalava com `ci_errs`, então um juiz que
        # achava bloqueador novo a cada rodada (sem CI) re-disparava pra sempre (#254). O ganho da
        # auto-correção zera por falta de CONTEXTO, não de tentativas.
        prior = await store.count_runs(run.tenant, run.repo, str(pr_number), "correct")
        if prior > _CORRECT_MAX_ATTEMPTS and (ci_errs or not verdict.approved):
            motivo = "a CI segue vermelha" if ci_errs else "o review ainda aponta bloqueadores"
            await github.comment_pr(
                run.repo,
                pr_number,
                f"🚩 Correção parada após {_CORRECT_MAX_ATTEMPTS} tentativas — {motivo}. "
                f"Precisa de olhar humano.\n{BOT_MARKER}",
            )
            await store.append_session_event(
                run.tenant, run.id, "message", moment,
                text=f"🚩 bound de correção ({_CORRECT_MAX_ATTEMPTS}) atingido — escala p/ humano",
            )
            await store.set_state(run.id, RunState.FAILED, moment)
            return

        # motor corrige NA branch do PR: CI vermelha PRIMEIRO (autoritativa), depois o review
        issues = list(verdict.issues)
        if ci_errs:
            issues = [f"A CI do repo REPROVOU — corrija EXATAMENTE isto:\n{ci_errs}"] + issues
        prompt = _correct_prompt(run.repo, pr_number, workdir, issues)
        # DEGRAU DE ESCALONAMENTO (#242 Fatia 3): 1ª correção no modelo base; da 2ª em diante (não
        # convergiu), a correção sobe pro MODELO FORTE antes de bater o bound e escalar p/ humano.
        # `prior` conta os runs de correct deste PR (inclui este).
        _forte_default = "openrouter,anthropic/claude-sonnet-4.6"
        modelo_forte = os.environ.get("ROBOTO_STRONG_MODEL", _forte_default)
        # mesmo guard do ciclo de impl: id forte ausente do ccr → fallback p/ base (senão a 2ª
        # correção morreria com unrecognized_model em vez de convergir).
        modelo_forte, _corr_reason = pin_or_fallback(modelo_forte, registered=registered_models())
        if _corr_reason:
            await store.append_session_event(
                run.tenant, run.id, "message", moment, text="⚠️ " + _corr_reason,
            )
        model_corr = modelo_forte if (prior >= _CORRECT_ESCALATE_AT and modelo_forte) else ""
        if model_corr:
            await store.append_session_event(
                run.tenant, run.id, "message", moment,
                text=f"⚡ correção não convergiu no base ({prior}ª rodada) → MODELO FORTE.",
            )
        await engine.start(
            RunSpec(
                tenant=run.tenant, repo=run.repo, workdir=workdir, prompt=prompt, model=model_corr
            )
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

        # commit resiliente ao prettier (mesmo motivo do run_pr_cycle): o correct tick tem commit
        # próprio e, sem isto, o pre-commit `prettier --check` barra os arquivos que a correção
        # tocou e MATA a correção (PR #254). Formata (determinístico) e re-tenta; bounded.
        await autoformat(workdir)
        _fmt_tries = 0
        while True:
            try:
                await git.commit_all(f"fix(review): corrige apontamentos (PR #{pr_number})")
                break
            except GitError as _exc:
                low = str(_exc).lower()
                if ("prettier" in low or "code style" in low) and _fmt_tries < _FMT_FIX_ATTEMPTS:
                    _fmt_tries += 1
                    await autoformat(workdir)
                    continue
                raise  # outro hook (doc-sync/i18n): sem turno de modelo aqui → propaga
        leak = await _guard_secrets(git, base, store=store, run=run, now=moment)  # H: antes do push
        if leak:
            raise SecretLeakError(leak)  # correção vazou segredo → bloqueia (push nunca sai sujo)
        await git.push(branch)  # force-push atualiza o MESMO PR

        again = await _review_now(previas=list(verdict.issues))
        if ci_errs:
            # a CI re-roda async no commit novo; o poller re-avalia (bounded). Fica pendente.
            body = "🔁 Correção da CI aplicada — a CI vai re-rodar no novo commit."
            final = RunState.VERIFYING
        elif again.approved:
            body = "✅ Correção aplicada — review re-aprovado."
            final = RunState.VERIFYING
        else:
            body = "🔁 Correção aplicada; ainda restam pontos:\n- " + "\n- ".join(again.issues)
            final = RunState.FAILED
        await github.comment_pr(
            run.repo, pr_number, body + f"\n\n_(correção do fleet, reviewer≠autor)_\n{BOT_MARKER}"
        )
        await store.set_state(run.id, final, moment)
    except Exception as exc:  # noqa: BLE001 — falha não pode deixar o run preso em RUNNING
        await store.set_state(run.id, RunState.FAILED, moment)
        op = classify_provider_error(str(exc))  # billing/cota do provider → msg clara, não bug
        await store.append_session_event(
            run.tenant, run.id, "message", moment,
            text=op or f"⚠️ correção falhou: {exc}",
        )
