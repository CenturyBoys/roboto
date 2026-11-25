"""Grafo de issues (árvore/DAG) para o cockpit: cruza as NOSSAS dependências (gravadas no corpo da
issue pelo breakdown/refino) com as NATIVAS do GitHub (sub-issues, tracked, cross-refs).

Função PURA e testável: recebe as issues abertas (com corpo) + as arestas nativas já resolvidas e
devolve ``nodes``/``edges`` — SEM I/O. Quem busca no GitHub (REST + GraphQL) é o cliente/console;
aqui só se cruza e deduplica. As NOSSAS deps são a fonte PRIMÁRIA; as nativas enriquecem.

Arestas (``kind``), sempre no sentido "pai/bloqueador → dependente" (facilita montar a árvore):
- ``epic-child``       — "Parte do épico #N" no corpo da filha (N é o épico). NOSSA.
- ``depends-on``       — "Depende de #N" / "blocked by #N" no corpo (reusa ``app/deps.blocked_by``);
                         sentido = filha → bloqueadora (quem depende aponta para quem bloqueia).
- ``subissue-native``  — sub-issue / trackedIssues nativos do GitHub (pai → filha). NATIVA.
- ``xref``             — "mentioned in #N" (cross-reference do timeline). NATIVA, só ENTRE issues
                         conhecidas (enriquecimento ruidoso: PRs/issues fechadas ficam de fora).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from roboto.agents.breakdown import is_epic
from roboto.app.deps import blocked_by

# Pai-épico declarado no corpo da filha. DUAS convenções no mundo real (eram inconsistentes — o
# #286 usava "Epico: #73" e ficava ÓRFÃO da árvore/driver, parecendo épico de topo):
#   1) "Parte do épico #N"  — como o breakdown_apply grava nas sub-issues.
#   2) "Epico: #N" / "**Épico:** #N"  — campo declarado (tolera markdown `**` e acento).
# Exige "parte do" OU o `:` (forma-DECLARAÇÃO) pra não casar prosa solta ("do épico #N — fatia…").
_EPIC_PARENT = re.compile(
    r"parte do [eé]pico\s*#(\d+)|[eé]pico\s*:\s*\**\s*#(\d+)", re.IGNORECASE
)


@dataclass(frozen=True)
class RawIssue:
    """Issue aberta crua, como vem do GitHub (precisa do CORPO p/ parsear as nossas deps)."""

    number: int
    title: str
    body: str
    labels: list[str]
    state: str | None = None


@dataclass(frozen=True)
class IssueNode:
    number: int
    title: str
    labels: list[str]
    is_epic: bool
    state: str | None


@dataclass(frozen=True)
class IssueEdge:
    source: int  # pai/bloqueador
    target: int  # filha/dependente
    kind: str  # epic-child | depends-on | subissue-native | xref


@dataclass(frozen=True)
class IssueGraph:
    nodes: list[IssueNode]
    edges: list[IssueEdge]
    has_cycle: bool  # ciclo detectado (best-effort) — a UI deve desenhar sem travar


def epic_parents(body: str) -> list[int]:
    """Épicos a que este corpo diz pertencer ("Parte do épico #N" OU "Epico: #N"), sem repetição."""
    nums: list[int] = []
    for m in _EPIC_PARENT.finditer(body or ""):
        n = int(m.group(1) or m.group(2))  # uma das duas convenções casa por match
        if n not in nums:
            nums.append(n)
    return nums


def build_graph(
    issues: Sequence[RawIssue], native_edges: Iterable[tuple[int, int, str]] = ()
) -> IssueGraph:
    """Cruza as NOSSAS deps (do corpo) com as NATIVAS (já resolvidas) e devolve o grafo deduplicado.

    Dedup por ``(source, target, kind)``: a mesma aresta nativa vinda de dois lados (``parent`` e
    ``subIssues``) colapsa; arestas de KINDS diferentes convivem (épico-nosso × sub-issue-nativa).
    ``xref`` só entra se ambas as pontas forem issues conhecidas (corta o ruído de PRs/fechadas).
    """
    nodes = [
        IssueNode(i.number, i.title, list(i.labels), is_epic(i.title, i.body), i.state)
        for i in issues
    ]
    known = {n.number for n in nodes}

    edges: list[IssueEdge] = []
    seen: set[tuple[int, int, str]] = set()

    def add(source: int, target: int, kind: str) -> None:
        if source == target:  # auto-laço não é dependência real
            return
        key = (source, target, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append(IssueEdge(source=source, target=target, kind=kind))

    for i in issues:
        for epic in epic_parents(i.body):  # "Parte do épico #N": N (pai) → esta (filha)
            add(epic, i.number, "epic-child")
        for blocker in blocked_by(i.body):  # "Depende de #N": esta (filha) → N (bloqueadora)
            add(i.number, blocker, "depends-on")

    for source, target, kind in native_edges:
        if kind == "xref" and (source not in known or target not in known):
            continue
        add(source, target, kind)

    return IssueGraph(nodes=nodes, edges=edges, has_cycle=_has_cycle(edges))


def _has_cycle(edges: Sequence[IssueEdge]) -> bool:
    """DFS com 3 cores sobre o grafo dirigido inteiro: há aresta de retorno (ciclo)? Best-effort —
    um épico que (por engano) depende de uma filha, ou refs circulares, não podem travar a UI."""
    adjacency: dict[int, list[int]] = {}
    for e in edges:
        adjacency.setdefault(e.source, []).append(e.target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {}

    def visit(node: int) -> bool:
        color[node] = GRAY
        for nxt in adjacency.get(node, ()):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return True
            if c == WHITE and visit(nxt):
                return True
        color[node] = BLACK
        return False

    return any(color.get(node, WHITE) == WHITE and visit(node) for node in list(adjacency))
