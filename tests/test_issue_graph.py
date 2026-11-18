"""Mapa de issues (árvore/DAG): função pura ``build_graph`` + endpoint ``GET /issues/tree``.

Cobre: épico→filhas ("Parte do épico #N"), depends-on ("Depende de #N"), ciclo best-effort, merge
das NOSSAS deps com as NATIVAS do GitHub, e o corte de ``xref`` entre issues desconhecidas.
"""

from __future__ import annotations

import httpx

from roboto.app.issue_graph import RawIssue, build_graph
from roboto.orchestrator.model import Error
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok, Result
from roboto.web.console import build_console

_TOKEN = "console-secret"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _edges(graph: object) -> set[tuple[int, int, str]]:
    return {(e.source, e.target, e.kind) for e in graph.edges}  # type: ignore[attr-defined]


def test_epic_child_and_depends_on_from_body() -> None:
    issues = [
        RawIssue(1, "Épico: motor vivo", "guarda-chuva", [], "open"),
        RawIssue(2, "sub A", "Pontos\n\nParte do épico #1", [], "open"),
        RawIssue(3, "sub B", "Depende de #2\n\nParte do épico #1", [], "open"),
    ]
    graph = build_graph(issues)
    assert {n.number: n.is_epic for n in graph.nodes} == {1: True, 2: False, 3: False}
    assert (1, 2, "epic-child") in _edges(graph)
    assert (1, 3, "epic-child") in _edges(graph)
    assert (3, 2, "depends-on") in _edges(graph)  # filha → bloqueadora
    assert graph.has_cycle is False


def test_merge_nossas_e_nativas_dedup() -> None:
    issues = [
        RawIssue(1, "pai", "", [], "open"),
        RawIssue(2, "filha", "Parte do épico #1", [], "open"),
    ]
    # nativa repete a hierarquia pai→filha por dois caminhos (parent e subIssues) + 1 xref conhecido
    native = [(1, 2, "subissue-native"), (1, 2, "subissue-native"), (2, 1, "xref")]
    graph = build_graph(issues, native)
    edges = _edges(graph)
    assert (1, 2, "epic-child") in edges  # a nossa
    assert (1, 2, "subissue-native") in edges  # a nativa (kind distinto convive)
    assert (2, 1, "xref") in edges
    # dedup: a aresta nativa duplicada não vira duas
    assert sum(1 for e in graph.edges if e.kind == "subissue-native") == 1


def test_xref_para_issue_desconhecida_e_cortado() -> None:
    issues = [RawIssue(2, "filha", "", [], "open")]
    # #99 não está entre os nós (PR ou issue fechada) → xref é ruído e não entra
    graph = build_graph(issues, [(99, 2, "xref"), (2, 99, "xref")])
    assert _edges(graph) == set()


def test_cycle_is_detected_without_breaking() -> None:
    issues = [
        RawIssue(1, "a", "Depende de #2", [], "open"),
        RawIssue(2, "b", "Depende de #1", [], "open"),  # ciclo 1↔2
    ]
    graph = build_graph(issues)
    assert graph.has_cycle is True
    assert len(graph.nodes) == 2  # não trava nem perde nós


# --- endpoint ----------------------------------------------------------------------------------


class _FakeIssues:
    """IssueSource mínimo p/ o /issues/tree: corpo com nossas deps + arestas nativas injetadas."""

    def __init__(
        self,
        full: list[tuple[int, str, str, list[str], str]],
        native: list[tuple[int, int, str]] | None = None,
        native_err: bool = False,
    ) -> None:
        self._full = full
        self._native = native or []
        self._native_err = native_err

    async def list_open_issues_full(
        self, repo: str, *, limit: int = 20
    ) -> Result[list[tuple[int, str, str, list[str], str]], Error]:
        return Ok(self._full)

    async def native_issue_links(
        self, repo: str, numbers: list[int]
    ) -> Result[list[tuple[int, int, str]], Error]:
        if self._native_err:
            return Err(Error("github", "graphql indisponível"))
        return Ok(self._native)


def _client(store: InMemoryStore, issues: object) -> httpx.AsyncClient:
    app = build_console(
        store, tenant="acme", token=_TOKEN, issues=issues, default_repo="acme/app"  # type: ignore[arg-type]
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://console")


async def test_tree_endpoint_merges_and_requires_auth() -> None:
    store = InMemoryStore()
    src = _FakeIssues(
        full=[
            (1, "Épico X", "guarda-chuva", ["epic"], "open"),
            (2, "sub A", "Parte do épico #1", [], "open"),
            (3, "sub B", "Depende de #2\nParte do épico #1", [], "open"),
        ],
        native=[(1, 2, "subissue-native")],
    )
    async with _client(store, src) as c:
        assert (await c.get("/issues/tree")).status_code == 401  # exige token
        data = (await c.get("/issues/tree", headers=_AUTH)).json()
    assert data["repo"] == "acme/app"
    assert [n["number"] for n in data["nodes"]] == [1, 2, 3]
    assert next(n for n in data["nodes"] if n["number"] == 1)["is_epic"] is True
    edges = {(e["from"], e["to"], e["kind"]) for e in data["edges"]}
    assert (1, 2, "epic-child") in edges
    assert (3, 2, "depends-on") in edges
    assert (1, 2, "subissue-native") in edges
    assert data["has_cycle"] is False


async def test_tree_degrades_when_native_fails() -> None:
    # GraphQL nativo indisponível → o mapa ainda sai com as NOSSAS deps (fonte primária).
    store = InMemoryStore()
    src = _FakeIssues(
        full=[(2, "sub A", "Parte do épico #1", [], "open")], native_err=True
    )
    async with _client(store, src) as c:
        data = (await c.get("/issues/tree", headers=_AUTH)).json()
    assert [n["number"] for n in data["nodes"]] == [2]
    assert {(e["from"], e["to"], e["kind"]) for e in data["edges"]} == {(1, 2, "epic-child")}
