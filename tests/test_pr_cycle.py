"""Amarração do ciclo (motor→git→PR→review→correção) com fakes — determinístico, CI."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.pr_cycle import process_pr_run_tick, run_pr_cycle
from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.github.app import IssueRef
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error, GithubEvent
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok, Result

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

    async def prepare_branch(self, name: str) -> None:
        self.branches.append(name)

    async def commit_all(self, message: str) -> None:
        self.commits.append(message)

    async def push(self, name: str) -> None:
        self.pushes.append(name)


_READY_BODY = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] z\n## DoD\n- [ ] ci"


class _FakeGithub:
    def __init__(self, existing_pr: int | None = None, ready_issue: bool = True) -> None:
        self.opened = 0
        self.comments: list[str] = []
        self._existing = existing_pr
        self._ready = ready_issue

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        body = _READY_BODY if self._ready else "só um esqueleto"
        return Ok(("título", body))

    async def find_open_pr(self, repo: str, head_branch: str) -> Result[int | None, Error]:
        return Ok(self._existing)

    async def open_pr(
        self, repo: str, *, title: str, body: str, head: str, base: str = "main"
    ) -> Result[IssueRef, Error]:
        self.opened += 1
        return Ok(IssueRef(repo=repo, number=42, url="https://github.com/acme/app/pull/42"))

    async def get_pr_diff(self, repo: str, number: int) -> Result[str, Error]:
        return Ok("diff --git a/x b/x\n+linha")

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]:
        self.comments.append(body)
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
    result, engine, git, github = await _cycle(_SeqGateway(["VEREDITO: aprovado"]))
    assert result.approved is True
    assert result.attempts == 1
    assert len(engine.started) == 1
    assert github.opened == 1  # PR aberto uma vez
    assert git.pushes == ["roboto/run-1"]
    assert github.comments == ["✅ Review aprovado."]


async def test_cycle_corrects_then_approves() -> None:
    gw = _SeqGateway(["VEREDITO: reprovado\n- sem teste", "VEREDITO: aprovado"])
    result, engine, git, github = await _cycle(gw)
    assert result.approved is True
    assert result.attempts == 2
    assert len(engine.started) == 2  # re-implementou com o feedback
    assert github.opened == 1  # reaproveitou o mesmo PR
    assert len(git.pushes) == 2
    assert "correções" in github.comments[0]  # 1º review pediu correção


async def test_cycle_reuses_live_pr() -> None:
    # já existe um PR aberto p/ o branch -> não abre outro (idempotência, repo vivo)
    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub(existing_pr=99)
    gw = _SeqGateway(["VEREDITO: aprovado"])
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
    gw = _SeqGateway(["VEREDITO: reprovado\n- bug", "VEREDITO: reprovado\n- bug ainda"])
    result, engine, git, github = await _cycle(gw, max_attempts=2)
    assert result.approved is False
    assert result.attempts == 2
    assert result.issues == ["bug ainda"]


async def test_process_pr_run_tick_claims_and_sets_state() -> None:
    from roboto.orchestrator.model import RunState

    store = InMemoryStore()
    run = await _run(store)  # type: ignore[assignment]
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    gw = _SeqGateway(["VEREDITO: aprovado"])
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
