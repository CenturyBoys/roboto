"""Materializar o breakdown no GitHub (inc. 3): cria sub-issues encadeadas + linka no épico."""

from __future__ import annotations

from roboto.agents.breakdown import Breakdown, SubIssueSkeleton
from roboto.app.breakdown_apply import materialize_breakdown
from roboto.app.deps import blocked_by
from roboto.github.app import IssueRef
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class _FakeGithub:
    """Atribui números sequenciais (a partir de 100) e guarda corpos + comentários do épico."""

    def __init__(self, fail_on: int | None = None) -> None:
        self._next = 100
        self.created: list[tuple[int, str, str]] = []  # (number, title, body)
        self.epic_comments: list[tuple[int, str]] = []
        self._fail_on = fail_on  # falha ao criar a N-ésima (1-based)

    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]:
        if self._fail_on is not None and len(self.created) + 1 == self._fail_on:
            return Err(Error("github", "boom"))
        n = self._next
        self._next += 1
        self.created.append((n, title, body))
        return Ok(IssueRef(repo=repo, number=n, url=f"https://x/{n}"))

    async def comment_pr(self, repo: str, number: int, body: str) -> Result[None, Error]:
        self.epic_comments.append((number, body))
        return Ok(None)


def _bd() -> Breakdown:
    return Breakdown(
        items=[
            SubIssueSkeleton("ADR", ["escrever ADR"], depends_on_prev=False),
            SubIssueSkeleton("logger", ["mascarar PII"], depends_on_prev=True),
            SubIssueSkeleton("gate check:logs", ["varrer no CI"], depends_on_prev=True),
        ]
    )


async def test_cria_em_ordem_encadeado() -> None:
    gh = _FakeGithub()
    res = await materialize_breakdown(gh, "o/r", epic_number=66, breakdown=_bd())
    assert isinstance(res, Ok)
    nums = [c.number for c in res.value]
    assert nums == [100, 101, 102]
    bodies = {t: b for (_, t, b) in gh.created}
    # 1ª não depende de ninguém; 2ª depende da 1ª (#100); 3ª depende da 2ª (#101)
    assert blocked_by(bodies["ADR"]) == []
    assert blocked_by(bodies["logger"]) == [100]
    assert blocked_by(bodies["gate check:logs"]) == [101]
    # todas referenciam o épico
    assert all("épico #66" in b for b in bodies.values())


async def test_comenta_indice_no_epico() -> None:
    gh = _FakeGithub()
    await materialize_breakdown(gh, "o/r", epic_number=66, breakdown=_bd())
    assert len(gh.epic_comments) == 1
    number, body = gh.epic_comments[0]
    assert number == 66
    assert "#100" in body and "#101" in body and "#102" in body


async def test_item_independente_no_meio_nao_encadeia() -> None:
    bd = Breakdown(
        items=[
            SubIssueSkeleton("A", ["x"], depends_on_prev=False),
            SubIssueSkeleton("B", ["y"], depends_on_prev=False),  # DEPENDE: nenhuma
        ]
    )
    gh = _FakeGithub()
    await materialize_breakdown(gh, "o/r", 66, bd)
    bodies = {t: b for (_, t, b) in gh.created}
    assert blocked_by(bodies["B"]) == []  # não encadeou


async def test_dependencia_nomeada_pendura_no_item_certo() -> None:
    # DAG: o 3º item depende do 1º (índice 0), NÃO do imediatamente anterior
    bd = Breakdown(
        items=[
            SubIssueSkeleton("schema", ["campos"], depends_on_prev=False),
            SubIssueSkeleton("scheduler", ["worker"], depends_on_prev=True),  # depende do schema
            SubIssueSkeleton("quórum", ["regra"], depends_on_prev=False, depends_on_index=0),
        ]
    )
    gh = _FakeGithub()
    res = await materialize_breakdown(gh, "o/r", 66, bd)
    assert isinstance(res, Ok)
    bodies = {t: b for (_, t, b) in gh.created}
    assert blocked_by(bodies["scheduler"]) == [100]  # encadeou no schema (#100)
    # NOMEADO no schema (#100), não no scheduler (#101)
    assert blocked_by(bodies["quórum"]) == [100]


async def test_para_na_primeira_falha() -> None:
    gh = _FakeGithub(fail_on=2)  # falha ao criar a 2ª
    res = await materialize_breakdown(gh, "o/r", 66, _bd())
    assert isinstance(res, Err)
    assert len(gh.created) == 1  # só a 1ª foi criada
    assert gh.epic_comments == []  # não comenta índice numa cadeia incompleta


async def test_breakdown_vazio() -> None:
    gh = _FakeGithub()
    res = await materialize_breakdown(gh, "o/r", 66, Breakdown(items=[]))
    assert isinstance(res, Ok)
    assert res.value == []
    assert gh.created == [] and gh.epic_comments == []
