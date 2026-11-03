"""Amarração do ciclo (motor→git→PR→review→correção) com fakes — determinístico, CI."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.pr_cycle import process_correct_tick, process_pr_run_tick, run_pr_cycle
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

    async def prepare_branch(self, name: str) -> None:
        self.branches.append(name)

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
        self.reviews: list[str] = []  # corpos de submit_review (review estruturado, Trilha D)
        self._existing = existing_pr
        self._ready = ready_issue
        self._custom_body = custom_body

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        if self._custom_body is not None:
            return Ok(("título", self._custom_body))
        body = _READY_BODY if self._ready else "só um esqueleto"
        return Ok(("título", body))

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]:
        return Ok(self._existing)

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main"
    ) -> Result[IssueRef, Error]:
        if self.open_fails:
            return Err(Error("github", "403 Pull requests: write ausente"))
        self.opened += 1
        return Ok(IssueRef(repo=repo, number=42, url="https://github.com/acme/app/pull/42"))

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

    async def set_issue_state(self, repo: str, number: int, state: str) -> Result[None, Error]:
        self.issue_states.append((number, state))
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
