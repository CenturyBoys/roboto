"""Amarração do ciclo (motor→git→PR→review→correção) com fakes — determinístico, CI."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.git_ops import GitError
from roboto.app.pr_cycle import (
    _should_polish_minors,
    process_correct_tick,
    process_pr_run_tick,
    run_pr_cycle,
)
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.github.app import IssueRef
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Engine, Error, GithubEvent, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok, Result

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


class _SeqGateway:
    """ModelGateway que devolve vereditos em sequência (um por review)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies

    async def complete(self, messages: list[ChatMessage], tier: Tier) -> Result[Completion, Error]:
        reply = self._replies.pop(0)
        return Ok(Completion(text=reply, model="stub"))


class _FakeGit:
    def __init__(self) -> None:
        self.branches: list[str] = []
        self.commits: list[str] = []
        self.pushes: list[str] = []
        self.checked_out: list[str] = []
        # diff NÃO-vazio por default (motor editou algo); #144 testa o caso vazio setando "".
        self.diff_text = "diff --git a/x.py b/x.py\n+edit"
        self.reverts: list[tuple[str, str, str]] = []  # revert (H): (base, source, revert_branch)
        self.revert_ok = True  # o teste de conflito seta False
        self.reset_bases: list[str] = []  # #225: bases p/ onde o run limpou o /work

    async def prepare_branch(self, name: str) -> None:
        self.branches.append(name)

    async def reset_to_base(self, base: str) -> None:
        self.reset_bases.append(base)  # #225: isolamento por run (limpa /work p/ a base)

    async def working_changes(self) -> list[str]:
        return []  # #226: árvore de trabalho (fake vazio — diag best-effort)

    baseline_red_output = ""  # #247: subclasses setam p/ simular pre-commit vermelho na base

    async def precommit_baseline(self) -> str:
        return self.baseline_red_output

    async def checkout_remote(self, name: str) -> None:
        self.checked_out.append(name)

    async def commit_all(self, message: str) -> None:
        self.commits.append(message)

    async def push(self, name: str) -> None:
        self.pushes.append(name)

    async def log_since(self, base: str) -> str:
        return "- " + "\n- ".join(self.commits) if self.commits else ""

    async def diff(self, base: str) -> str:
        return self.diff_text

    async def revert_range(self, base: str, source_branch: str, revert_branch: str) -> bool:
        self.reverts.append((base, source_branch, revert_branch))
        return self.revert_ok


_READY_BODY = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] z\n## DoD\n- [ ] ci"
# Review ESTRUTURADO (Trilha D): reprova = 1 bloco FINDING bloqueador; aprova = "" (sem finding).
_FIND_REPROVA = (
    "FINDING\nseveridade: bloqueador\narquivo: a.ts\nlinha: 1\nconfianca: alta\n"
    "titulo: falta teste\nevidencia: x\nrecomendacao: adicionar teste\nEND"
)
# triagem de CI (ci_triage): classifica a falha como NOSSA → a correção no PR segue normal. O
# process_correct_tick, com ci_errs não-vazio, faz 1 chamada extra ao gateway (a triagem) entre o
# review e o re-review — por isso os testes de CI vermelha injetam esta resposta.
_TRIAGE_NOSSO = (
    "CATEGORIA: nosso_codigo\nNOSSO: sim\nCONFIANCA: alta\n"
    "TITULO:\nRESUMO: erro de tipo em arquivo do PR\nDEDUP:"
)
# triagem classifica a falha como vuln de dependência PRÉ-EXISTENTE (não nossa) → abre issue, não
# força o PR a consertar.
_TRIAGE_SEGURANCA = (
    "CATEGORIA: dependencia_seguranca\nNOSSO: nao\nCONFIANCA: alta\n"
    "TITULO: Vuln HIGH ReDoS no pacote effect\n"
    "RESUMO: bump effect p/ >=3.22.1 (transitiva via prisma)\nDEDUP: GHSA-7589-6fvf-x4pw"
)


class _FakeGithub:
    def __init__(
        self,
        existing_pr: int | None = None,
        ready_issue: bool = True,
        custom_body: str | None = None,
    ) -> None:
        self.opened = 0
        self.open_fails = False  # #144: simula open_pr sem permissão (PAT sem PR:write)
        self.assignees: list[tuple[int, str]] = []  # #150: (issue_number, login)
        self.comments: list[str] = []
        self.issue_states: list[tuple[int, str]] = []  # revert (H): (issue_number, state)
        self.blocker_state = "open"  # gate de dependência (J): estado da issue bloqueadora
        self.labels: list[str] = []  # gate de prontidão por label (#1046): status:blocked etc.
        self.created_issues: list[tuple[str, str]] = []  # self-heal (#322): deps auto-abertas
        self.issue_bodies: list[tuple[int, str]] = []  # self-heal wire (#322): corpo reescrito
        self.reviews: list[str] = []  # corpos de submit_review (review estruturado, Trilha D)
        self.ci_errs = ""  # #233: saída de CI vermelha (default = CI verde); testes setam
        self.opened_draft: list[bool] = []  # P0b: draft= de cada open_pr
        self.pr_labels: list[tuple[int, str]] = []  # P0b: add_pr_label (needs-human na escalada)
        self.readied: list[int] = []  # P0b: PRs promovidos de draft→ready (só na aprovação)
        self.ready_fails = False  # P0b: simula GraphQL recusando a promoção
        self._existing = existing_pr
        self._ready = ready_issue
        self._custom_body = custom_body

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        if self._custom_body is not None:
            return Ok(("título", self._custom_body))
        body = _READY_BODY if self._ready else "só um esqueleto"
        return Ok(("título", body))

    async def get_issue_labels(self, repo: str, number: int) -> Result[list[str], Error]:
        return Ok(list(self.labels))

    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]:
        self.created_issues.append((title, body))
        n = 900 + len(self.created_issues)
        return Ok(IssueRef(repo=repo, number=n, url=f"https://github.com/{repo}/issues/{n}"))

    async def list_open_issues_rich(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str, list[str]]], Error]:
        return Ok([])  # nada rastreado → self-heal cria

    async def list_prs_audit(
        self, repo: str, *, limit: int = 100
    ) -> Result[list[dict[str, object]], Error]:
        return Ok([])  # sem PR mergeado → nada "já satisfeito"

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]:
        return Ok(self._existing)

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main",
        draft: bool = False,
    ) -> Result[IssueRef, Error]:
        if self.open_fails:
            return Err(Error("github", "403 Pull requests: write ausente"))
        self.opened += 1
        self.opened_draft.append(draft)
        return Ok(IssueRef(repo=repo, number=42, url="https://github.com/acme/app/pull/42"))

    async def add_pr_label(self, repo: str, number: int, label: str) -> Result[None, Error]:
        self.pr_labels.append((number, label))
        return Ok(None)

    async def mark_pr_ready(self, repo: str, number: int) -> Result[None, Error]:
        if self.ready_fails:
            return Err(Error("github", "graphql recusou"))
        self.readied.append(number)
        return Ok(None)

    async def add_assignee(self, repo: str, number: int, login: str) -> Result[None, Error]:
        self.assignees.append((number, login))
        return Ok(None)

    async def get_pr_head(self, repo: str, number: int) -> Result[str, Error]:
        return Ok(f"feature/pr-{number}")

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]:
        return Ok("diff --git a/x b/x\n+linha")

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]:
        self.comments.append(body)
        return Ok(None)

    async def check_failures(self, repo: str, number: int) -> Result[str, Error]:
        return Ok(self.ci_errs)  # #233: "" = CI verde; não-vazio = erro real da CI

    async def set_issue_state(self, repo: str, number: int, state: str) -> Result[None, Error]:
        self.issue_states.append((number, state))
        return Ok(None)

    async def set_issue_state_label(
        self, repo: str, number: int, label: str
    ) -> Result[None, Error]:
        self.labels.append(label)  # self-heal (#322): to-do/auto nos filhos, blocked no pai
        return Ok(None)

    async def update_issue(
        self, repo: str, number: int, *, title: str, body: str
    ) -> Result[None, Error]:
        self.issue_bodies.append((number, body))  # self-heal wire (#322): aresta Depende de #N
        return Ok(None)

    async def get_issue_state(self, repo: str, number: int) -> Result[str, Error]:
        return Ok(self.blocker_state)  # gate de dependência (J): "open" segura; "closed" libera

    async def submit_review(
        self, repo: str, number: int, body: str, comments: list[tuple[str, int, str]]
    ) -> Result[None, Error]:
        self.reviews.append(body)
        return Ok(None)


async def _run(store: InMemoryStore) -> object:
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="7", agent="impl", idempotency_key="k"
    )
    run, _ = await store.insert_run_if_absent(event, _T0)
    return run


async def _cycle(gateway: _SeqGateway, *, max_attempts: int = 3):  # type: ignore[no-untyped-def]
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    result = await run_pr_cycle(
        engine=engine, gateway=gateway, github=github, git=git, run=run,  # type: ignore[arg-type]
        workdir="/work/acme/app", reviewer="review", max_attempts=max_attempts,
    )
    return result, engine, git, github


async def test_cycle_approves_first_try() -> None:
    result, engine, git, github = await _cycle(_SeqGateway([""]))
    assert result.approved is True
    assert result.attempts == 1
    assert len(engine.started) == 1
    assert github.opened == 1  # PR aberto uma vez
    assert git.pushes == ["roboto/run-1"]
    assert github.comments == []  # review vai por submit_review (inline), não comment_pr
    assert any("sem apontamentos" in r for r in github.reviews)


async def test_cycle_corrects_then_approves() -> None:
    gw = _SeqGateway([_FIND_REPROVA, ""])
    result, engine, git, github = await _cycle(gw)
    assert result.approved is True
    assert result.attempts == 2
    assert len(engine.started) == 2  # re-implementou com o feedback
    assert github.opened == 1  # reaproveitou o mesmo PR
    assert len(git.pushes) == 2
    assert any("bloqueador" in r for r in github.reviews)  # 1º review reprovou (estruturado)


async def test_correction_resumes_coder_session() -> None:
    # B: a correção RESUME a sessão do coder (mesmo contexto de quem implementou), não do zero.
    gw = _SeqGateway([_FIND_REPROVA, ""])
    _, engine, _, _ = await _cycle(gw)
    assert len(engine.started) == 2
    assert engine.started[0].resume_session_id is None  # 1ª impl: sessão nova
    assert engine.started[1].resume_session_id == "stub-session"  # correção: resume do coder


async def test_forte_finalize_rascunho_base_correcao_forte() -> None:
    # #242 (proativo): ROBOTO_FORTE_FINALIZE=1 → rascunho (1º turno) no BASE; a correção (turno com
    # feedback) sobe pro MODELO FORTE. O base escreve, o forte FECHA.
    import os

    gw = _SeqGateway([_FIND_REPROVA, ""])  # 1º review reprova → força 1 turno de correção
    old_f = os.environ.get("ROBOTO_FORTE_FINALIZE")
    old_m = os.environ.get("ROBOTO_STRONG_MODEL")
    os.environ["ROBOTO_FORTE_FINALIZE"] = "1"
    os.environ["ROBOTO_STRONG_MODEL"] = "openrouter,modelo-forte-teste"
    try:
        _, engine, _, _ = await _cycle(gw)
    finally:
        for k, v in (("ROBOTO_FORTE_FINALIZE", old_f), ("ROBOTO_STRONG_MODEL", old_m)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    assert len(engine.started) == 2
    assert engine.started[0].model == ""  # rascunho: BASE (default do ccr)
    assert engine.started[1].model == "openrouter,modelo-forte-teste"  # correção: FORTE


async def test_porta_ci_local_bloqueia_e_corrige(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # roda a MESMA porta do CI (lint) ANTES do push: vermelho → motor corrige → verde → push.
    import json as _json

    (tmp_path / "package.json").write_text(_json.dumps({"scripts": {"lint": "eslint"}}))
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    calls = {"n": 0}

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        calls["n"] += 1
        if calls["n"] == 1:  # 1ª passada: lint vermelho; depois da correção: verde
            return 1, "30:15 error Unexpected any @typescript-eslint/no-explicit-any"
        return 0, "ok"

    result = await run_pr_cycle(
        engine=engine, gateway=_SeqGateway([""]), github=github, git=git, run=run,
        workdir=str(tmp_path), reviewer="review", store=store, now=_T0, ci_runner=runner,
    )
    assert result.approved is True
    assert git.pushes  # verde após a correção → empurrou (PR nasce verde)
    assert any("verificação LOCAL" in s.prompt for s in engine.started)  # houve turno de fix de CI
    events = await store.session_events(run.id, 0, 90)
    assert any("CI local `lint` reprovou" in e.text for e in events)
    assert any("CI local verde" in e.text for e in events)


async def test_porta_ci_local_vermelho_persistente_escala_humano(tmp_path) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    # lint vermelho SEMPRE → esgota tentativas → NÃO abre PR, escala p/ humano (não nasce vermelho).
    import json as _json

    (tmp_path / "package.json").write_text(_json.dumps({"scripts": {"lint": "eslint"}}))
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "erro de lint que o motor não resolve"

    raised = False
    try:
        await run_pr_cycle(
            engine=engine, gateway=_SeqGateway([""]), github=github, git=git, run=run,
            workdir=str(tmp_path), reviewer="review", store=store, now=_T0, ci_runner=runner,
        )
    except RuntimeError:
        raised = True
    assert raised
    assert git.pushes == []  # NÃO empurrou — PR não nasce vermelho
    assert github.opened == 0
    events = await store.session_events(run.id, 0, 90)
    assert any("segue vermelho" in e.text and "humano" in e.text for e in events)


async def test_escada_gerente_resolve_antes_do_humano(tmp_path) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    # ESCADA (fatia 1, #322): worker esgota o CI vermelho → GERENTE assume e resolve → PR nasce
    # (sem escalar pro humano). O gerente fake marca `ran`; o runner então fica verde.
    import json as _json

    (tmp_path / "package.json").write_text(_json.dumps({"scripts": {"lint": "eslint"}}))
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    state = {"ran": False}

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return (0, "ok") if state["ran"] else (1, "erro que o worker não resolve")

    class _MgrEngine(StubEngine):
        async def events(self):  # type: ignore[no-untyped-def]
            state["ran"] = True  # o gerente "resolveu" o estado travado
            for ev in self._script:
                yield ev

    result = await run_pr_cycle(
        engine=engine, gateway=_SeqGateway([""]), github=github, git=git, run=run,
        workdir=str(tmp_path), reviewer="review", store=store, now=_T0, ci_runner=runner,
        make_manager=lambda: _MgrEngine([EngineEvent(EngineEventKind.FINISHED)]),
    )
    assert result.approved is True  # gerente resolveu → PR nasceu verde
    assert git.pushes
    events = await store.session_events(run.id, 0, 120)
    assert any("gerente (forte) assumindo" in e.text for e in events)
    assert any("gerente resolveu" in e.text for e in events)


async def test_escada_gerente_falha_escala_humano(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # ESCADA: se NEM o gerente resolve (runner sempre vermelho), aí sim escala pro humano.
    import json as _json

    (tmp_path / "package.json").write_text(_json.dumps({"scripts": {"lint": "eslint"}}))
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "erro que nem o gerente resolve"

    raised = False
    try:
        await run_pr_cycle(
            engine=engine, gateway=_SeqGateway([""]), github=github, git=git, run=run,
            workdir=str(tmp_path), reviewer="review", store=store, now=_T0, ci_runner=runner,
            make_manager=lambda: StubEngine([EngineEvent(EngineEventKind.FINISHED)]),
        )
    except RuntimeError:
        raised = True
    assert raised
    assert git.pushes == [] and github.opened == 0  # PR não nasce vermelho
    events = await store.session_events(run.id, 0, 120)
    assert any("worker + gerente" in e.text and "humano" in e.text for e in events)


async def test_porta_ci_local_infra_nao_trava(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # vermelho de INFRA (DB fora) não é culpa do modelo → NÃO realimenta, surfa e SEGUE (push ok).
    import json as _json

    (tmp_path / "package.json").write_text(_json.dumps({"scripts": {"test": "vitest"}}))
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "Error: connect ECONNREFUSED 127.0.0.1:5432"

    result = await run_pr_cycle(
        engine=engine, gateway=_SeqGateway([""]), github=github, git=git, run=run,
        workdir=str(tmp_path), reviewer="review", store=store, now=_T0, ci_runner=runner,
    )
    assert result.approved is True
    assert git.pushes  # infra não trava: seguiu e empurrou
    events = await store.session_events(run.id, 0, 90)
    # mensagem HONESTA (sem setup no repo p/ subir o ambiente): surfa e aponta o CI do GitHub.
    assert any("CI local" in e.text and "OBRIGATÓRIO" in e.text for e in events)


async def test_cycle_reuses_live_pr() -> None:
    # já existe um PR aberto p/ o branch -> não abre outro (idempotência, repo vivo)
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub(existing_pr=99)
    gw = _SeqGateway([""])
    result = await run_pr_cycle(
        engine=engine,
        gateway=gw,  # type: ignore[arg-type]
        github=github,
        git=git,
        run=run,
        workdir="/work/acme/app",
        reviewer="review",
    )
    assert result.approved is True
    assert github.opened == 0  # reaproveitou o PR #99, não abriu novo
    assert result.pr is not None
    assert result.pr.number == 99


async def test_cycle_gives_up_at_max() -> None:
    gw = _SeqGateway([_FIND_REPROVA, _FIND_REPROVA])
    result, engine, git, github = await _cycle(gw, max_attempts=2)
    assert result.approved is False
    assert result.attempts == 2
    assert len(result.issues) == 1 and "falta teste" in result.issues[0]  # feedback estruturado


async def test_cycle_blocks_push_on_secret_leak() -> None:
    # H: diff com segredo -> _guard_secrets levanta SecretLeakError ANTES do push; PR não abre.
    import pytest

    from roboto.app.secret_scan import SecretLeakError

    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    git.diff_text = 'diff --git a/c.py b/c.py\n+TOKEN = "ghp_' + "a" * 36 + '"\n'
    with pytest.raises(SecretLeakError):
        await run_pr_cycle(
            engine=engine, gateway=_SeqGateway([""]), github=github, git=git,  # type: ignore[arg-type]
            run=run, workdir="/work/acme/app", reviewer="review",
        )
    assert git.pushes == []  # não empurrou o segredo
    assert github.opened == 0  # não abriu PR


async def test_cycle_autofixes_secret_then_pushes() -> None:
    # H (auto-correção): diff vaza segredo -> motor corrige (diff limpa) e o push SEGUE.
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])

    class _LeakyThenClean(_FakeGit):
        async def diff(self, base: str) -> str:
            # vaza até o motor "corrigir" (após o 2º commit = o de correção) -> então limpa
            if len(self.commits) < 2:
                return 'diff --git a/c.py b/c.py\n+TOKEN = "ghp_' + "a" * 36 + '"\n'
            return "diff --git a/x.py b/x.py\n+edit"

    git, github = _LeakyThenClean(), _FakeGithub()
    result = await run_pr_cycle(
        engine=engine, gateway=_SeqGateway(["", ""]),  # type: ignore[arg-type]
        github=github, git=git, run=run, workdir="/work/acme/app",
        reviewer="review", store=store, now=_T0,
    )
    assert git.pushes  # empurrou: o segredo foi removido pela auto-correção
    assert github.opened == 1  # PR aberto normalmente
    assert len(engine.started) >= 2  # rodou o turno de correção (impl + fix)
    assert result.approved
    events = await store.session_events(run.id, 0, 50)
    assert any("secret-scan" in e.text for e in events)  # registrou o bloqueio/retry no feed


async def test_cycle_escala_modelo_forte_no_hook() -> None:
    # #242: o modelo base esgota o hook → degrau de escalonamento força 1 turno no MODELO FORTE
    # antes de desistir. Se o forte tb não resolver → escala p/ humano.
    import os

    store = InMemoryStore()
    run = await _run(store)  # issue pequena (_READY_BODY) → tier não-forte → base = default (qwen)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])

    class _I18nHookForever(_FakeGit):
        async def commit_all(self, message: str) -> None:
            raise GitError("check:i18n ✖ i18n — 5 erro(s) (bloqueia)")

    old = os.environ.get("ROBOTO_STRONG_MODEL")
    os.environ["ROBOTO_STRONG_MODEL"] = "openrouter,modelo-forte-teste"
    try:
        raised = False
        try:
            await run_pr_cycle(
                engine=engine, gateway=_SeqGateway([]),  # type: ignore[arg-type]
                github=_FakeGithub(), git=_I18nHookForever(), run=run, workdir="/work/acme/app",
                reviewer="review", store=store, now=_T0,
            )
        except GitError:
            raised = True
    finally:
        if old is None:
            os.environ.pop("ROBOTO_STRONG_MODEL", None)
        else:
            os.environ["ROBOTO_STRONG_MODEL"] = old

    assert raised
    # houve 1 turno com o MODELO FORTE (spec.model = o forte de teste)
    assert any(s.model == "openrouter,modelo-forte-teste" for s in engine.started)
    events = await store.session_events(run.id, 0, 90)
    assert any("MODELO FORTE" in e.text for e in events)  # registrou o degrau
    assert any("Precisa de humano" in e.text for e in events)  # forte tb não cedeu → humano


async def test_cycle_baseline_vermelho_surfa_divida_preexistente() -> None:
    # #247: o pre-commit do repo-alvo já falha na BASE (dívida pré-existente, ex.: 555 i18n) → o
    # fleet surfa isso e NÃO culpa a mudança do modelo.
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])

    class _BaseRedI18n(_FakeGit):
        baseline_red_output = "check:i18n ✖ 555 erro(s) (bloqueia)"

        async def commit_all(self, message: str) -> None:
            raise GitError("check:i18n ✖ 555 erro(s) (bloqueia)")

    raised = False
    try:
        await run_pr_cycle(
            engine=engine, gateway=_SeqGateway([]),  # type: ignore[arg-type]
            github=_FakeGithub(), git=_BaseRedI18n(), run=run, workdir="/work/acme/app",
            reviewer="review", store=store, now=_T0,
        )
    except GitError:
        raised = True
    assert raised
    events = await store.session_events(run.id, 0, 90)
    assert any("vermelho na BASE" in e.text for e in events)  # avisou no início
    assert any("pré-existente" in e.text and "não é a sua mudança" in e.text for e in events)


async def test_cycle_hook_nao_prettier_escala_humano() -> None:
    # exec #80: hook NÃO-prettier (i18n) não cede após N tentativas → escala LIMPO p/ humano
    # (mensagem clara no feed), em vez de FAILED seco com GitError cru.
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])

    class _I18nHookForever(_FakeGit):
        async def commit_all(self, message: str) -> None:
            raise GitError("check:i18n ✖ i18n — 5 erro(s) (bloqueia): chave faltando")

    raised = False
    try:
        await run_pr_cycle(
            engine=engine, gateway=_SeqGateway([]),  # type: ignore[arg-type]
            github=_FakeGithub(), git=_I18nHookForever(), run=run, workdir="/work/acme/app",
            reviewer="review", store=store, now=_T0,
        )
    except GitError:
        raised = True
    assert raised  # esgotou o hook e propagou (FAILED a jusante)
    events = await store.session_events(run.id, 0, 80)
    assert any("Precisa de humano" in e.text for e in events)  # escalou limpo


async def test_prettier_barra_apos_turno_do_modelo_reformata_e_segue() -> None:
    # #245: prettier barra → hook i18n barra (motor cria locales) → prettier barra arquivos novos.
    # Formatar à mão (modelo) NUNCA casa com o prettier; o harness tem de RE-FORMATAR após o turno
    # do modelo. Com o fix o ciclo recupera e empurra; sem ele, esgotava e ia FAILED.
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])

    class _PrettierAfterModelTurn(_FakeGit):
        def __init__(self) -> None:
            super().__init__()
            self._fails = [
                "prettier --check (staged) failed",
                "doc-sync/i18n hook: missing translation key",  # motor cria arquivos novos aqui
                "prettier --check (staged) failed",  # os arquivos novos não estão formatados
                "prettier --check (staged) failed",
            ]

        async def commit_all(self, message: str) -> None:
            if self._fails:
                raise GitError(self._fails.pop(0))
            self.commits.append(message)

    git, github = _PrettierAfterModelTurn(), _FakeGithub()
    result = await run_pr_cycle(
        engine=engine, gateway=_SeqGateway(["", "", ""]),  # type: ignore[arg-type]
        github=github, git=git, run=run, workdir="/work/acme/app",
        reviewer="review", store=store, now=_T0,
    )
    assert git.commits  # fechou o commit (não ficou preso no prettier)
    assert git.pushes and github.opened == 1 and result.approved
    assert len(engine.started) >= 2  # houve ao menos 1 turno de correção de hook (i18n)
    events = await store.session_events(run.id, 0, 80)
    assert any("hook" in e.text for e in events)  # registrou a barrada de hook no feed


async def test_retry_injects_previous_failure_into_prompt() -> None:
    # B/G: no retry (attempt>0), o motivo da falha anterior (mesmo run) entra no prompt do motor.
    import dataclasses

    store = InMemoryStore()
    run = await _run(store)
    await store.append_session_event(
        "acme", run.id, "message", _T0,
        text="⚠️ execução falhou: segredo atribuído (heurística) [eyJh…*** (44 chars)]",
    )
    run2 = dataclasses.replace(run, attempt=1)  # simula o retry
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    await run_pr_cycle(
        engine=engine, gateway=_SeqGateway(["", ""]),  # type: ignore[arg-type]
        github=github, git=git, run=run2, workdir="/work/acme/app",
        reviewer="review", store=store, now=_T0,
    )
    assert engine.started  # rodou
    assert "APRENDIZADO DA TENTATIVA ANTERIOR" in engine.started[0].prompt
    assert "eyJh" in engine.started[0].prompt  # carregou o motivo concreto


async def test_first_attempt_has_no_learning_block() -> None:
    # attempt 0: sem histórico de falha → prompt limpo (não inventa aprendizado).
    store = InMemoryStore()
    run = await _run(store)  # attempt 0
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await run_pr_cycle(
        engine=engine, gateway=_SeqGateway(["", ""]),  # type: ignore[arg-type]
        github=_FakeGithub(), git=_FakeGit(), run=run, workdir="/work/acme/app",
        reviewer="review", store=store, now=_T0,
    )
    assert "APRENDIZADO DA TENTATIVA ANTERIOR" not in engine.started[0].prompt


async def test_process_pr_run_tick_fails_and_warns_on_secret_leak() -> None:
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    leaky = _FakeGit()
    leaky.diff_text = "+key = AKIA" + "A" * 16 + "\n"
    github = _FakeGithub()
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: leaky, now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]
    assert github.opened == 0  # PR não aberto
    events = await store.session_events(run.id, 0, 50)
    assert any("secret-scan" in e.text for e in events)  # avisou no feed


async def test_tick_sem_aprovacao_registra_motivo_no_feed() -> None:
    # review reprova em TODAS as tentativas → FAILED. O motivo tem de aparecer no FEED (console),
    # não só no Telegram — senão o run vira `failed` com a última msg do implement (ex.: o aviso
    # benigno de CI local INFRA) como único rastro, parecendo que o CI local falhou.
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    gw = _SeqGateway([_FIND_REPROVA, _FIND_REPROVA, _FIND_REPROVA])  # reprova as 3 tentativas
    github = _FakeGithub()
    await process_pr_run_tick(
        engine, gw, github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]
    events = await store.session_events(run.id, 0, 50)
    assert any("sem aprovação" in e.text for e in events)  # motivo visível no console
    assert any("falta teste" in e.text for e in events)  # pendências do review surfadas no feed
    # #3: cada review reprovado deixa o veredito no feed (não só o agregado final do encerramento)
    assert any("Review: reprovou" in e.text for e in events)
    # P0b: PR nasceu DRAFT, NÃO foi promovido (review não aprovou) e ganhou label needs-human →
    # GitHub não deixa mergear (furo do run-1047/#399 fechado).
    assert github.opened_draft == [True]
    assert github.readied == []
    assert (42, "needs-human") in github.pr_labels


async def test_tick_aprovado_promove_pr_a_ready() -> None:
    # P0b: review aprova → o PR (nascido draft) é PROMOVIDO a ready-for-review (humano mergeia).
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]  # "" = aprovado
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.VERIFYING  # type: ignore[attr-defined]
    assert github.opened_draft == [True]  # nasceu draft
    assert github.readied == [42]  # promovido na aprovação
    assert all(lab != "needs-human" for _, lab in github.pr_labels)


async def test_tick_aprovado_mas_promocao_falha_avisa_e_fica_draft() -> None:
    # P0b lado seguro: se o GraphQL recusar a promoção, o PR FICA draft e o feed avisa (não mergeia
    # por acidente nem quebra o run).
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    github.ready_fails = True
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.VERIFYING  # type: ignore[attr-defined]
    assert github.readied == []  # não promoveu
    events = await store.session_events(run.id, 0, 50)
    assert any("não consegui tirar do draft" in e.text for e in events)


class _RaisingEngine:
    """Motor que levanta um erro na partida — p/ testar o tratamento de falha do tick."""

    def __init__(self, message: str) -> None:
        self._message = message

    @property
    def engine(self):  # type: ignore[no-untyped-def]
        return Engine.CLAUDE_CODE

    @property
    def session_id(self) -> str:
        return ""

    async def start(self, spec):  # type: ignore[no-untyped-def]
        raise RuntimeError(self._message)

    async def events(self):  # type: ignore[no-untyped-def]
        if False:
            yield None

    async def respond(self, answer: str):  # type: ignore[no-untyped-def]
        return Ok(None)

    async def interrupt(self):  # type: ignore[no-untyped-def]
        return Ok(None)


async def test_transient_error_requeues_with_backoff_not_failed() -> None:
    # B: erro transitório de provedor (402) → re-enfileira com backoff (retoma sozinho), não FAILED
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = _RaisingEngine("API Error: 402 would exceed your available credit")
    await process_pr_run_tick(
        engine, _SeqGateway([""]), _FakeGithub(), store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    r = store._runs[run.id]  # type: ignore[attr-defined]
    assert r.state is RunState.QUEUED  # re-enfileirado (não FAILED)
    assert r.attempt == 1 and r.next_attempt_at is not None  # backoff armado


async def test_permanent_error_goes_failed() -> None:
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = _RaisingEngine("git push rejected: non-fast-forward")  # permanente
    await process_pr_run_tick(
        engine, _SeqGateway([""]), _FakeGithub(), store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]


async def test_blocked_label_issue_waits_not_implemented() -> None:
    # Gate de prontidão por LABEL (#1046): issue `status:blocked` NÃO é implementada (espera), mesmo
    # com DoR estrutural ok — o label é o veredito humano que o parser de `#N` não vê.
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    github.labels = ["status:blocked"]
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.WAITING  # type: ignore[attr-defined]
    assert len(engine.started) == 0  # não chegou a rodar o motor
    assert any("não-pronta" in c for c in github.comments)  # motivo comentado na issue


async def test_self_heal_abre_deps_nomeadas_faltantes(monkeypatch) -> None:  # type: ignore[no-untyped-def]  # noqa: E501
    # SELF-HEAL (fatia 2, #322): issue bloqueada que depende de "T1/T2" (nomeadas, sem issue) →
    # o harness ABRE a issue de cada dep e comenta no pai. Toggle ROBOTO_SELF_HEAL_DEPS.
    monkeypatch.setenv("ROBOTO_SELF_HEAL_DEPS", "1")
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub(
        custom_body="**Depende de:** **T1** (`bracket.ts` puro) e **T2** (migration). Resto.",
    )
    github.labels = ["status:blocked"]  # fica bloqueada (dep faltante); o self-heal abre as deps
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert len(github.created_issues) == 2  # T1 e T2 abertas
    assert any("bracket.ts" in t for t, _ in github.created_issues)
    events = await store.session_events(run.id, 0, 60)
    assert any("self-heal" in e.text for e in events)


class _StallingEngine(StubEngine):
    """Motor que emite 1 evento e então TRAVA (idle-timeout → TimeoutError) no meio do turno."""

    async def events(self):  # type: ignore[no-untyped-def]
        yield EngineEvent(EngineEventKind.TOOL_CALL, tool="Edit")
        raise TimeoutError  # watchdog de inatividade (stream do ccr/OpenRouter mudo)


async def test_stall_requeues_once_and_persists_native_session() -> None:
    # Motor travado (idle-timeout): re-enfileira 1x (auto-retry) E grava o id nativo — p/ o humano
    # "responder depois do timeout" e retomar a MESMA sessão com contexto (não do zero).
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = _StallingEngine([])
    await process_pr_run_tick(
        engine, _SeqGateway([""]), _FakeGithub(), store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    r = store._runs[run.id]  # type: ignore[attr-defined]
    assert r.state is RunState.QUEUED  # stall → re-enfileirado (não FAILED terminal)
    assert r.attempt == 1  # auto-retry 1x
    # id nativo persistido MESMO com o stall → o resume humano acha a sessão
    sessions = await store.sessions_for_execution(run.id)
    assert sessions and sessions[0].native_session_id == "stub-session"


async def test_blocked_issue_waits_not_implemented() -> None:
    # J: issue "bloqueada por #79" com a #79 ABERTA → WAITING, não implementa
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    body = _READY_BODY + "\n\nbloqueada por #79"
    github = _FakeGithub(custom_body=body)
    github.blocker_state = "open"  # #79 ainda aberta
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.WAITING  # type: ignore[attr-defined]
    assert len(engine.started) == 0  # NÃO implementou
    assert any("Bloqueada por #79" in c for c in github.comments)


async def test_blocked_issue_implements_when_blocker_closed() -> None:
    # se a #79 está FECHADA, o bloqueio não segura — implementa normalmente
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    github = _FakeGithub(custom_body=_READY_BODY + "\n\nblocked by #79")
    github.blocker_state = "closed"  # #79 já fechou
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.VERIFYING  # type: ignore[attr-defined]
    assert len(engine.started) == 1  # implementou (bloqueador fechado)


async def test_self_assign_on_claim() -> None:
    # #150: ao pegar o run de impl, o fleet se atribui como assignee da issue
    store = InMemoryStore()
    await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0, self_assign_login="potter-bot",
    )
    assert (7, "potter-bot") in github.assignees  # issue 7 atribuída ao fleet


async def test_open_pr_failure_fails_run_not_review() -> None:
    # #144: open_pr falho NÃO vira PR nº 0 silencioso — o run FALHA, sem review sobre diff vazio
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    github.open_fails = True
    await process_pr_run_tick(
        engine, _SeqGateway([""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]
    assert github.reviews == []  # não revisou nada


async def test_empty_diff_fails_run() -> None:
    # #144: diff vazio (motor não editou) → run falha explicitamente
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git = _FakeGit()
    git.diff_text = ""  # motor não editou nada
    await process_pr_run_tick(
        engine, _SeqGateway([""]), _FakeGithub(), store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: git, now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]


async def test_implement_prompt_injects_recalled_memory() -> None:
    # second brain (G): o harness recalla um fato relevante e injeta no prompt de implement.
    store = InMemoryStore()
    await _run(store)
    await store.remember(
        "acme", "decisão: o título do recurso segue o padrão X", kind="decisao", ref="", now=_T0
    )
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await process_pr_run_tick(
        engine, _SeqGateway([""]), _FakeGithub(), store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    prompt = engine.started[0].prompt
    assert "MEMÓRIA RELEVANTE" in prompt
    assert "o título do recurso segue o padrão X" in prompt


async def test_process_pr_run_tick_claims_and_sets_state() -> None:
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED, tokens_in=1000, tokens_out=200)])
    gw = _SeqGateway([""])
    await process_pr_run_tick(
        engine,
        gw,  # type: ignore[arg-type]
        _FakeGithub(),
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: _FakeGit(),
        now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.VERIFYING  # type: ignore[attr-defined]
    # sessão do motor (D23) gravada com o id nativo
    sessions = await store.sessions_for_execution(run.id)
    assert len(sessions) == 1
    assert sessions[0].native_session_id == "stub-session"
    # medição de token (llm_call): grava o MOTOR (frontier) + o REVIEW (judge)
    calls = await store.llm_calls("acme", 10)
    assert len(calls) == 2
    tiers = {c.tier for c in calls}
    assert "frontier" in tiers and "judge" in tiers
    assert sum(c.tokens_in + c.tokens_out for c in calls) == 1200  # do motor


async def test_process_pr_run_tick_skeleton_asks_and_waits() -> None:
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # issue_id="7" (numérico) -> busca a issue e checa o DoR
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub(ready_issue=False)  # issue esqueleto
    await process_pr_run_tick(
        engine,
        _SeqGateway([]),  # type: ignore[arg-type]
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: _FakeGit(),
        now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.WAITING  # type: ignore[attr-defined]
    assert engine.started == []  # NÃO implementou (esqueleto)
    assert any("incompleta" in c for c in github.comments)  # pediu ao humano


async def test_process_pr_run_tick_skeleton_echoes_to_telegram() -> None:
    # run vindo do Telegram (origin_chat_id) -> DoR incompleto ecoa no chat, não só no GitHub (D30)
    store = InMemoryStore()
    event = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="7", agent="impl",
        idempotency_key="k-tg", origin_chat_id="555",
    )
    await store.insert_run_if_absent(event, _T0)
    await process_pr_run_tick(
        StubEngine([EngineEvent(EngineEventKind.FINISHED)]),
        _SeqGateway([]),  # type: ignore[arg-type]
        _FakeGithub(ready_issue=False),
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: _FakeGit(),
        now=lambda: _T0,
    )
    effects = await store.pending_effects(10)
    tg = [e for e in effects if e.kind == "telegram_notify"]
    assert len(tg) == 1
    assert tg[0].payload["chat_id"] == "555"
    assert "#7" in tg[0].payload["text"]


async def test_process_pr_run_tick_empty_queue_is_noop() -> None:
    store = InMemoryStore()
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    await process_pr_run_tick(
        engine,
        _SeqGateway([]),  # type: ignore[arg-type]
        _FakeGithub(),
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: _FakeGit(),
        now=lambda: _T0,
    )
    assert engine.started == []  # fila vazia -> nada rodou


async def test_pr_run_tick_blocks_definicao() -> None:
    # #158: task de DEFINIÇÃO (keyword ADR/decidir, sem critérios) -> NÃO implementa, fica WAITING.
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub(custom_body="Precisamos decidir o ADR de rate limiting. Sem critérios.")
    await process_pr_run_tick(
        engine,
        _SeqGateway([]),  # type: ignore[arg-type]
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: _FakeGit(),
        now=lambda: _T0,
    )
    assert engine.started == []  # NÃO implementou (é definição)
    assert store._runs[run.id].state is RunState.WAITING  # type: ignore[attr-defined]
    assert any("defini" in c.lower() for c in github.comments)


async def test_correct_tick_fixes_pr_on_its_branch() -> None:
    # B: corrige um PR já aberto NO branch do PR (checkout) → review → corrige → push → re-review.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="221", agent="correct", idempotency_key="c"
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine(
        [
            EngineEvent(EngineEventKind.MESSAGE, text="corrigido"),
            EngineEvent(EngineEventKind.FINISHED, tokens_in=800, tokens_out=200),
        ]
    )
    git, github = _FakeGit(), _FakeGithub()
    gw = _SeqGateway([_FIND_REPROVA, ""])  # reprova->aprova
    await process_correct_tick(
        engine,
        gw,  # type: ignore[arg-type]
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: git,
        now=lambda: _T0,
    )
    assert git.checked_out == ['feature/pr-221']  # entrou NA branch do PR (não resetou p/ base)
    assert len(engine.started) == 1  # o motor corrigiu
    assert git.pushes == ['feature/pr-221']  # force-push atualizou o MESMO PR
    assert store._runs[run.id].state is RunState.VERIFYING  # re-review aprovou
    assert any('re-aprovado' in c for c in github.comments)
    # custo do coder da correção registrado (antes ficava 0 → sumia do Custos)
    calls = await store.llm_calls("acme", 10)
    assert any(c.tokens_in == 800 and c.tokens_out == 200 for c in calls)


async def test_correct_tick_prettier_barra_reformata_e_segue() -> None:
    # #254: a correção edita, mas o pre-commit `prettier --check` barra os arquivos tocados. O
    # correct tick tem commit próprio — precisa de autoformat+retry (igual ao impl), senão morre.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="221", agent="correct", idempotency_key="cp"
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine(
        [
            EngineEvent(EngineEventKind.MESSAGE, text="corrigido"),
            EngineEvent(EngineEventKind.FINISHED),
        ]
    )

    class _PrettierOnce(_FakeGit):
        def __init__(self) -> None:
            super().__init__()
            self._barrou = False

        async def commit_all(self, message: str) -> None:
            if not self._barrou:
                self._barrou = True
                raise GitError("prettier --check (staged) failed")
            self.commits.append(message)

    git, github = _PrettierOnce(), _FakeGithub()
    gw = _SeqGateway([_FIND_REPROVA, ""])  # reprova → corrige → aprova
    await process_correct_tick(
        engine, gw, github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: git, now=lambda: _T0,
    )
    assert git.commits and git.pushes == ["feature/pr-221"]  # reformatou e empurrou (não morreu)
    assert store._runs[run.id].state is RunState.VERIFYING  # type: ignore[attr-defined]


async def test_correct_tick_rereview_recebe_contexto_previo() -> None:
    # convergência (#254): o RE-review tem de receber os pontos anteriores como contexto_previo —
    # senão revisa do zero e inventa bloqueadores novos a cada rodada, e o PR nunca fecha.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="221", agent="correct", idempotency_key="cx"
    )
    await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])

    class _CapturingGateway:
        def __init__(self, replies: list[str]) -> None:
            self._replies = list(replies)
            self.calls: list[list[ChatMessage]] = []

        async def complete(
            self, messages: list[ChatMessage], tier: Tier
        ) -> Result[Completion, Error]:
            self.calls.append(messages)
            return Ok(Completion(text=self._replies.pop(0), model="stub"))

    gw = _CapturingGateway([_FIND_REPROVA, ""])  # review inicial reprova → corrige → re-review ok
    git, github = _FakeGit(), _FakeGithub()
    await process_correct_tick(
        engine, gw, github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: git, now=lambda: _T0,
    )
    # a 2ª chamada ao juiz (re-review) deve carregar o ponto anterior ("falta teste")
    assert len(gw.calls) == 2
    rereview_txt = " ".join(m.content for m in gw.calls[1])
    assert "falta teste" in rereview_txt


async def test_ci_recheck_nao_falso_aprova_pr_escalado() -> None:
    # Fix 2 (#1054/#402): poll-correct-ci NÃO pode FORÇAR "aprovado" num PR ESCALADO (needs-human) —
    # nesse PR o review nunca aprovou (bloqueador em aberto); CI verde ≠ review ok. Re-revisa.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="402", agent="correct",
        idempotency_key="poll-correct-ci:acme/app:402",
    )
    await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    github.labels = ["needs-human"]  # o PR foi escalado pelo impl
    gw = _SeqGateway([_FIND_REPROVA, "", "", ""])  # o re-review reprova (bloqueador ainda lá)
    await process_correct_tick(
        engine, gw, github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    # não forçou "aprovado" (re-revisou e o bloqueador segue) → NÃO postou o falso "review aprovado"
    assert not any("review aprovado" in c for c in github.comments)


async def test_correct_tick_escala_coder_forte_na_2a_rodada() -> None:
    # #242 Fatia 3: 1ª correção no base; da 2ª em diante (não convergiu) o coder sobe pro FORTE.
    import os

    store = InMemoryStore()
    for k in ("c1", "c2"):  # 2 runs de correct no MESMO PR → prior=2 → escala
        await store.insert_run_if_absent(
            GithubEvent(tenant="acme", repo="acme/app", issue_id="221",
                        agent="correct", idempotency_key=k),
            _T0,
        )
    engine = StubEngine(
        [
            EngineEvent(EngineEventKind.MESSAGE, text="corrigido"),
            EngineEvent(EngineEventKind.FINISHED),
        ]
    )
    gw = _SeqGateway([_FIND_REPROVA, ""])  # reprova → corrige → aprova
    git, github = _FakeGit(), _FakeGithub()
    old = os.environ.get("ROBOTO_STRONG_MODEL")
    os.environ["ROBOTO_STRONG_MODEL"] = "openrouter,modelo-forte-teste"
    try:
        await process_correct_tick(
            engine, gw, github, store,  # type: ignore[arg-type]
            tenant="acme", workdir_root="/work", reviewer="review",
            git_factory=lambda ws: git, now=lambda: _T0,
        )
    finally:
        if old is None:
            os.environ.pop("ROBOTO_STRONG_MODEL", None)
        else:
            os.environ["ROBOTO_STRONG_MODEL"] = old
    # a correção rodou no MODELO FORTE (2ª rodada) e empurrou
    assert any(s.model == "openrouter,modelo-forte-teste" for s in engine.started)
    assert git.pushes == ["feature/pr-221"]


async def test_correct_tick_approved_pr_is_noop() -> None:
    # PR já aprovado no review -> não edita, não dá push, comenta "nada a corrigir", vai a DONE.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="221", agent="correct", idempotency_key="c2"
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    await process_correct_tick(
        engine,
        _SeqGateway([""]),  # type: ignore[arg-type]
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: git,
        now=lambda: _T0,
    )
    assert engine.started == []  # nada a corrigir -> motor não roda
    assert git.pushes == []
    assert store._runs[run.id].state is RunState.DONE


async def test_correct_tick_ci_red_forces_correction_even_if_judge_approves() -> None:
    # #233: o juiz APROVA o diff, mas a CI está VERMELHA → corrige mesmo assim, com o erro REAL da
    # CI como feedback autoritativo. Era o buraco do #252 (juiz não via o erro de tipo do tsc).
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="221", agent="correct", idempotency_key="c3"
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine(
        [
            EngineEvent(EngineEventKind.MESSAGE, text="corrigindo tsc"),
            EngineEvent(EngineEventKind.FINISHED, tokens_in=100, tokens_out=50),
        ]
    )
    git, github = _FakeGit(), _FakeGithub()
    github.ci_errs = "✖ verify: Typecheck\n  route.test.ts:20 TS2345 Request não é NextRequest"
    await process_correct_tick(
        engine,
        # juiz aprova (rodadas), triagem classifica NOSSO → corrige mesmo assim (CI manda)
        _SeqGateway(["", _TRIAGE_NOSSO, ""]),  # type: ignore[arg-type]
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: git,
        now=lambda: _T0,
    )
    assert len(engine.started) == 1  # corrigiu APESAR do juiz aprovar (a CI mandou)
    assert git.pushes == ["feature/pr-221"]
    assert store._runs[run.id].state is RunState.VERIFYING  # CI re-roda no commit novo
    assert "TS2345" in engine.started[0].prompt  # o erro REAL da CI foi pro prompt da correção


async def test_correct_tick_bound_escalates_after_max_attempts() -> None:
    # #233: esgotou o bound e a CI segue vermelha → NÃO corrige mais, escala p/ humano (anti-loop).
    store = InMemoryStore()
    for i in range(4):  # 4 runs 'correct' do MESMO PR > _CORRECT_MAX_ATTEMPTS (3)
        await store.insert_run_if_absent(
            GithubEvent(
                tenant="acme", repo="acme/app", issue_id="221",
                agent="correct", idempotency_key=f"c-{i}",
            ),
            _T0,
        )
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    github.ci_errs = "✖ verify: ainda vermelha"
    await process_correct_tick(
        engine,
        _SeqGateway(["", _TRIAGE_NOSSO]),  # type: ignore[arg-type]  # review + triagem (NOSSO)
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: git,
        now=lambda: _T0,
    )
    assert engine.started == []  # bateu o bound -> não corrige
    assert git.pushes == []
    assert any("🚩" in c and "humano" in c for c in github.comments)  # escalou
    assert any(r.state is RunState.FAILED for r in store._runs.values())


async def test_correct_tick_ci_nao_nosso_abre_issue_e_nao_corrige() -> None:
    # pedido do dono: vuln de dep PRÉ-EXISTENTE (pnpm audit) não é nosso código → o AGENTE tria e a
    # política NÃO força este PR a consertar; abre issue dedicada (dedup) e segue.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="318", agent="correct", idempotency_key="sec"
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    github.ci_errs = "✖ scan: Audit (produção — high+)\n  high ReDoS in effect <=3.22.0"
    await process_correct_tick(
        engine,
        _SeqGateway(["", _TRIAGE_SEGURANCA]),  # type: ignore[arg-type]  # review aprova + triagem
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: git,
        now=lambda: _T0,
    )
    assert engine.started == []  # NÃO forçou correção (não é nosso código)
    assert git.pushes == []
    issues = [e for e in store._effects.values() if e.kind == "create_issue"]
    assert len(issues) == 1  # abriu UMA issue de follow-up
    assert "effect" in issues[0].payload["title"]
    assert "GHSA-7589-6fvf-x4pw" in issues[0].dedup_key  # deduplicada pela chave do GHSA
    evs = await store.session_events(run.id, 0, 90)
    assert any("Triagem de CI" in (e.text or "") for e in evs)
    assert store._runs[run.id].state is RunState.DONE  # review ok + vermelho alheio neutralizado


async def test_correct_tick_ci_recheck_nao_re_revisa_o_doc() -> None:
    # refino anti-churn: um run de CI-recheck (poll-correct-ci) NÃO re-revisa o doc — só tria a CI.
    # Mesmo com um review que REPROVARIA, não corrige o doc; o gateway só é chamado p/ a triagem.
    store = InMemoryStore()
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="318", agent="correct",
        idempotency_key="poll-correct-ci:acme/app:318:deadbeef",
    )
    run, _ = await store.insert_run_if_absent(ev, _T0)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    github.ci_errs = "✖ Security: failure (ReDoS in effect)"
    # 1 só reply no gateway = a TRIAGEM (o review do doc é PULADO no ci-recheck). Re-revisar
    # consumiria outra reply e estouraria a sequência.
    await process_correct_tick(
        engine,
        _SeqGateway([_TRIAGE_SEGURANCA]),  # type: ignore[arg-type]
        github,
        store,
        tenant="acme",
        workdir_root="/work",
        reviewer="review",
        git_factory=lambda ws: git,
        now=lambda: _T0,
    )
    assert engine.started == []  # não re-corrigiu o doc
    assert git.pushes == []  # não empurrou (sem churn de sha)
    assert len([e for e in store._effects.values() if e.kind == "create_issue"]) == 1  # abriu issue
    assert store._runs[run.id].state is RunState.DONE


# (removido: o gate de tamanho no impl foi revertido — contar critério é proxy ruim de épico; o
# right-sizing agora é advisory no refino (epic_signal/Jev). Cobertura: test_epic_signal.py.)


# --- fecha MENORES (ROBOTO_CLOSE_MINORS): passada BOUNDED de polimento, nunca falha o run ---

def _poli(**kw: object) -> bool:
    base = dict(
        aprovado=True, close_minors=True, n_minores=2,
        minor_done=False, review_calls=1, max_attempts=3,
    )
    base.update(kw)
    return _should_polish_minors(**base)  # type: ignore[arg-type]


def test_poli_menores_caso_feliz() -> None:
    # aprovou (0 bloqueador) + toggle + há menores + não poliu + há orçamento → faz a passada.
    assert _poli() is True


def test_poli_so_uma_passada() -> None:
    # já poliu uma vez (minor_done) → não poli de novo (conservador); aceita o que sobrar.
    assert _poli(minor_done=True) is False


def test_poli_respeita_orcamento() -> None:
    # na ÚLTIMA tentativa (review_calls == max_attempts) NÃO poli — sobra 1 volta p/ aceitar,
    # garantindo que um menor jamais derruba o run por esgotar o budget.
    assert _poli(review_calls=3, max_attempts=3) is False
    assert _poli(review_calls=2, max_attempts=3) is True


def test_poli_so_com_toggle_e_sem_bloqueador() -> None:
    assert _poli(close_minors=False) is False  # toggle desligado = comportamento antigo
    assert _poli(aprovado=False) is False  # tem bloqueador → correção normal, não polimento
    assert _poli(n_minores=0) is False  # aprovou limpo → nada a polir


# finding MENOR (não-bloqueante): review APROVA, mas aponta uma ressalva menor.
_FIND_MENOR = (
    "FINDING\nseveridade: menor\narquivo: a.ts\nlinha: 1\nconfianca: alta\n"
    "titulo: nome pouco claro\nevidencia: x\nrecomendacao: renomear a var\nEND"
)


async def test_close_minors_polimenta_e_aprova(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # fiação REAL (review()→correction_cycle→implement): toggle ON, review aprova COM um menor →
    # 1 passada de polimento (re-implementa com o menor injetado) → re-review limpo → aprovado.
    monkeypatch.setenv("ROBOTO_CLOSE_MINORS", "1")
    result, engine, _git, _gh = await _cycle(_SeqGateway([_FIND_MENOR, ""]))
    assert result.approved is True
    assert result.attempts == 2  # a volta extra = o polimento rodou
    assert len(engine.started) == 2  # re-implementou (o menor foi pro feedback)


async def test_close_minors_desligado_nao_polimenta(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # default (toggle OFF): menor não bloqueia e NÃO dispara polimento (comportamento antigo).
    monkeypatch.delenv("ROBOTO_CLOSE_MINORS", raising=False)
    result, engine, _git, _gh = await _cycle(_SeqGateway([_FIND_MENOR]))
    assert result.approved is True
    assert result.attempts == 1
    assert len(engine.started) == 1


async def test_close_minors_persistente_nunca_falha(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # SEGURANÇA: mesmo que o menor PERSISTA, aceita na review seguinte (1 passada só) — o run
    # NUNCA falha por um menor (é polimento, não bloqueio).
    monkeypatch.setenv("ROBOTO_CLOSE_MINORS", "1")
    gw = _SeqGateway([_FIND_MENOR, _FIND_MENOR])
    result, engine, _git, _gh = await _cycle(gw, max_attempts=3)
    assert result.approved is True  # aceitou o menor remanescente
    assert result.attempts == 2


async def test_close_minors_surfa_no_feed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # o polimento deixa rastro no feed (🧹) p/ o operador ver no cockpit.
    monkeypatch.setenv("ROBOTO_CLOSE_MINORS", "1")
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    await run_pr_cycle(
        engine=engine, gateway=_SeqGateway([_FIND_MENOR, ""]), github=github, git=git,  # type: ignore[arg-type]
        run=run, workdir="/work/acme/app", reviewer="review", store=store, now=_T0,
    )
    evs = await store.session_events(run.id, 0, 100)
    assert any("🧹" in (e.text or "") for e in evs)  # surfou "Fechando N menor(es)"


async def test_tick_ci_vermelha_nao_aprova_mesmo_sem_finding_do_juiz() -> None:
    # P1c: juiz "aprovaria" (sem finding), mas o CI está vermelho → review NÃO aprova (bloqueador de
    # CI determinístico) → run FAILED, PR fica draft + needs-human (não vira mergeável).
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    github.ci_errs = "tsc: error TS2345 — Type 'null' is not assignable"  # CI vermelho
    await process_pr_run_tick(
        # juiz aprovaria (sem finding) em toda tentativa; o CI vermelho é que reprova e re-tenta
        engine, _SeqGateway(["", "", "", ""]), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]
    assert github.readied == []  # não promovido (CI vermelho)
    assert (42, "needs-human") in github.pr_labels
    events = await store.session_events(run.id, 0, 50)
    assert any("CI vermelha" in e.text for e in events)


async def test_review_que_erra_nao_aprova_fail_closed() -> None:
    # #402: um review que NÃO RODA (erro de LLM/saldo/timeout) NÃO pode virar "aprovado" (era
    # fail-OPEN: `res.value if Ok else []` → [] → aprovado). Fail-CLOSED: o run NÃO aprova → o PR
    # fica draft + needs-human (não vira um falso "✅ aprovado").
    from roboto.orchestrator.model import RunState

    class _ErrGateway:
        async def complete(
            self, messages: list[ChatMessage], tier: Tier
        ) -> Result[Completion, Error]:
            return Err(Error("llm", "402 insufficient credits"))

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    github = _FakeGithub()
    await process_pr_run_tick(
        engine, _ErrGateway(), github, store,  # type: ignore[arg-type]
        tenant="acme", workdir_root="/work", reviewer="review",
        git_factory=lambda ws: _FakeGit(), now=lambda: _T0,
    )
    assert store._runs[run.id].state is RunState.FAILED  # type: ignore[attr-defined]
    assert github.readied == []  # NÃO promovido (review não aprovou)
    assert (42, "needs-human") in github.pr_labels
