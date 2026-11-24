"""Graph doctor — auditoria DETERMINÍSTICA do grafo de issues/dependências de um repo.

Motivação (épico #73): hoje o humano acha na mão as inconsistências do grafo (issue fechada que foi
revertida; esqueleto redundante pra fundação já pronta; dep em prosa que nunca virou `#N`; issue
fechada dependendo de abertas; órfão nunca refinado; ciclo). Isso é trabalho de harness. Este módulo
é a CAMADA DE DETECÇÃO: puro, sem I/O, testável — recebe o grafo já carregado e devolve findings.
O CARREGADOR (github→nós) e o HEAL (reabrir/fechar/repontar; seguro=auto, julgamento=gerente,
destrutivo=humano) ficam em cima disto, seguindo a escada determinismo→agente→humano.

Determinismo-primeiro: QUEM decide a cura pode ser o gerente; o QUE está quebrado é código.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IssueNode:
    number: int
    title: str
    state: str  # "open" | "closed"
    deps: list[int] = field(default_factory=list)  # #N que a bloqueiam (app/deps.py:blocked_by)
    named_deps: list[str] = field(default_factory=list)  # deps em PROSA (T1/T2) ainda não-`#N`
    state_reason: str = ""  # "completed" | "not_planned" | ""
    is_auto: bool = False  # esqueleto auto-aberto pelo self-heal (label `auto`)
    refined: bool = True  # passou pelo refino (DoR)? esqueleto nasce False
    age_days: int = 0  # idade da issue ABERTA (p/ órfão envelhecido)


@dataclass(frozen=True)
class PrNode:
    number: int
    state: str  # "open" | "merged" | "closed"
    title: str = ""  # título (p/ casar esqueleto redundante com fundação já feita)
    closes: list[int] = field(default_factory=list)  # issues que este PR fecha ("Closes #N")
    reverted_by: int | None = None  # nº do PR que REVERTE este (se houver)


@dataclass(frozen=True)
class GraphFinding:
    kind: str  # closed_dep_open | closed_but_reverted | redundant_skeleton | prose_unwired |
    #            aging_orphan | cycle
    issue: int
    detail: str
    heal: str  # cura sugerida: reopen | close_done | wire_or_refine | refine | break_cycle
    severity: str = "erro"  # erro | aviso


_ORPHAN_MAX_AGE_DAYS = 7


def closed_depending_on_open(issues: list[IssueNode]) -> list[GraphFinding]:
    """Issue FECHADA como completa que ainda depende de issue(s) ABERTA(s) → contradição (a #286 foi
    fechada dependendo de #397/#398 abertas). Done não pode depender de não-done."""
    aberta = {i.number for i in issues if i.state == "open"}
    out: list[GraphFinding] = []
    for i in issues:
        if i.state == "closed" and i.state_reason != "not_planned":
            pend = [d for d in i.deps if d in aberta]
            if pend:
                out.append(GraphFinding(
                    "closed_dep_open", i.number,
                    f"fechada como pronta mas depende de aberta(s): {pend}", "reopen",
                ))
    return out


def closed_but_reverted(issues: list[IssueNode], prs: list[PrNode]) -> list[GraphFinding]:
    """Issue fechada como COMPLETED pelo merge de um PR REVERTIDO (ou cujo PR não está mergeado) →
    o trabalho não existe mais; 'done' é mentira (a #286 via #399 revertido). Reabrir."""
    por_issue: dict[int, PrNode] = {}
    for p in prs:
        for n in p.closes:
            por_issue[n] = p
    out: list[GraphFinding] = []
    for i in issues:
        if i.state != "closed" or i.state_reason == "not_planned":
            continue
        pr = por_issue.get(i.number)
        if pr is None:
            continue
        if pr.reverted_by is not None:
            out.append(GraphFinding(
                "closed_but_reverted", i.number,
                f"fechada pelo PR #{pr.number}, revertido pelo PR #{pr.reverted_by}", "reopen",
            ))
        elif pr.state != "merged":
            out.append(GraphFinding(
                "closed_but_reverted", i.number,
                f"fechada mas o PR #{pr.number} que a fecharia está {pr.state} (não mergeado)",
                "reopen",
            ))
    return out


def prose_dep_unwired(issues: list[IssueNode]) -> list[GraphFinding]:
    """Issue ABERTA com dependência em PROSA (T1/T2…) que o gate por `#N` não enxerga → grafo
    incompleto; o driver a trata como pronta sem estar (raiz do incidente do #286)."""
    return [
        GraphFinding(
            "prose_unwired", i.number,
            f"dep em prosa não-wire-ada: {i.named_deps} (vire `Depende de #N` ou refine)",
            "wire_or_refine", "aviso",
        )
        for i in issues
        if i.state == "open" and i.named_deps
    ]


def redundant_skeleton(issues: list[IssueNode], prs: list[PrNode]) -> list[GraphFinding]:
    """Esqueleto `auto` ABERTO cujo título casa com um PR JÁ MERGEADO → fundação já existe; o
    self-heal abriu trabalho redundante (a #397 'T1 bracket.ts' vs. o PR #331 mergeado). Fechar."""
    titulos_merged = [(_norm(p.title), p.number) for p in prs if p.state == "merged" and p.title]
    out: list[GraphFinding] = []
    for i in issues:
        if i.state != "open" or not i.is_auto:
            continue
        alvo = _norm(i.title)
        for t, pr_n in titulos_merged:
            if t and _overlap(alvo, t):
                out.append(GraphFinding(
                    "redundant_skeleton", i.number,
                    f"esqueleto bate com PR mergeado #{pr_n} — fundação já feita", "close_done",
                    "aviso",
                ))
                break
    return out


def aging_orphans(issues: list[IssueNode], *, max_age_days: int = _ORPHAN_MAX_AGE_DAYS) -> list[
    GraphFinding
]:
    """Esqueleto `auto` ABERTO, NÃO-refinado e velho → ninguém refinou; está travando a cadeia em
    silêncio. Cutuca p/ refino (ou descarte)."""
    return [
        GraphFinding(
            "aging_orphan", i.number,
            f"esqueleto auto não-refinado há {i.age_days}d (> {max_age_days}d)", "refine", "aviso",
        )
        for i in issues
        if i.state == "open" and i.is_auto and not i.refined and i.age_days > max_age_days
    ]


def dependency_cycles(issues: list[IssueNode]) -> list[GraphFinding]:
    """Ciclo no grafo de `#N` (A dep B dep … dep A) → nada destrava nunca. Reporta um finding por nó
    envolvido num ciclo (detecção por DFS, só entre issues conhecidas)."""
    conhecidas = {i.number for i in issues}
    adj = {i.number: [d for d in i.deps if d in conhecidas] for i in issues}
    COR: dict[int, int] = {}  # 0=branco 1=cinza 2=preto
    em_ciclo: set[int] = set()

    def visita(n: int, pilha: list[int]) -> None:
        COR[n] = 1
        pilha.append(n)
        for m in adj.get(n, []):
            if COR.get(m, 0) == 1:  # aresta de retorno → ciclo
                em_ciclo.update(pilha[pilha.index(m):])
            elif COR.get(m, 0) == 0:
                visita(m, pilha)
        pilha.pop()
        COR[n] = 2

    for n in adj:
        if COR.get(n, 0) == 0:
            visita(n, [])
    return [
        GraphFinding("cycle", n, "faz parte de um ciclo de dependências", "break_cycle")
        for n in sorted(em_ciclo)
    ]


@dataclass(frozen=True)
class HealAction:
    issue: int
    kind: str  # a classe do finding
    action: str  # reopen | close_done | needs_refine | needs_human
    auto: bool  # pode o harness aplicar SOZINHO (sem humano)?
    detail: str


def plan_heal(findings: list[GraphFinding]) -> list[HealAction]:
    """Classifica cada finding numa ação de cura e decide o que é AUTO-seguro. Conservador (zero
    tolerância a cura errada): só **reabrir** é auto — é protetor, nunca perde trabalho. Fechar
    redundante, repontar e quebrar ciclo exigem JULGAMENTO (gerente propõe, humano confirma)."""
    mapa = {
        "reopen": ("reopen", True),
        "close_done": ("close_done", False),  # fechar é reversível, mas pode ser falso-positivo
        "wire_or_refine": ("needs_refine", False),
        "refine": ("needs_refine", False),
        "break_cycle": ("needs_human", False),
    }
    out: list[HealAction] = []
    for f in findings:
        action, auto = mapa.get(f.heal, ("needs_human", False))
        out.append(HealAction(f.issue, f.kind, action, auto, f.detail))
    return out


def audit_graph(
    issues: list[IssueNode], prs: list[PrNode] | None = None,
) -> list[GraphFinding]:
    """Roda TODOS os detectores e devolve os findings (erros antes dos avisos; estável)."""
    prs = prs or []
    achados = [
        *closed_but_reverted(issues, prs),
        *closed_depending_on_open(issues),
        *dependency_cycles(issues),
        *redundant_skeleton(issues, prs),
        *prose_dep_unwired(issues),
        *aging_orphans(issues),
    ]
    return sorted(achados, key=lambda f: (f.severity != "erro", f.issue))


# --- helpers internos ---


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _overlap(a: str, b: str) -> bool:
    """Metade das palavras-chave (≥4 letras) de ``a`` aparece em ``b`` → provável mesmo assunto."""
    pa = {w for w in a.split() if len(w) >= 4}
    pb = {w for w in b.split() if len(w) >= 4}
    if not pa:
        return False
    return len(pa & pb) / len(pa) >= 0.5
