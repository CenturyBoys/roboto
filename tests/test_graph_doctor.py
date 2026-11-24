"""Graph doctor — auditoria determinística do grafo de issues/deps (épico #73)."""

from __future__ import annotations

from roboto.app.graph_doctor import (
    GraphFinding,
    IssueNode,
    PrNode,
    audit_graph,
    closed_but_reverted,
    closed_depending_on_open,
    dependency_cycles,
    prose_dep_unwired,
    redundant_skeleton,
)


def _kinds(fs: list[GraphFinding]) -> set[str]:
    return {f.kind for f in fs}


def test_closed_depending_on_open_pega_contradicao() -> None:
    # #286: fechada como completa, mas depende de #398 ABERTA → contradição.
    issues = [
        IssueNode(286, "scheduler", "closed", deps=[398], state_reason="completed"),
        IssueNode(398, "T2 migration", "open"),
    ]
    fs = closed_depending_on_open(issues)
    assert len(fs) == 1 and fs[0].issue == 286 and fs[0].heal == "reopen"
    assert "398" in fs[0].detail


def test_closed_depending_on_open_ignora_not_planned() -> None:
    # fechada como 'not planned' (descartada) não é contradição.
    issues = [
        IssueNode(1, "x", "closed", deps=[2], state_reason="not_planned"),
        IssueNode(2, "y", "open"),
    ]
    assert closed_depending_on_open(issues) == []


def test_closed_but_reverted_reabre() -> None:
    # #286 fechada pelo #399, que foi revertido pelo #400 → reabrir.
    issues = [IssueNode(286, "scheduler", "closed", state_reason="completed")]
    prs = [
        PrNode(399, "merged", closes=[286], reverted_by=400),
        PrNode(400, "open", title="revert #399"),
    ]
    fs = closed_but_reverted(issues, prs)
    assert len(fs) == 1 and fs[0].issue == 286 and fs[0].heal == "reopen"
    assert "399" in fs[0].detail and "400" in fs[0].detail


def test_closed_but_pr_nao_mergeado_reabre() -> None:
    issues = [IssueNode(7, "x", "closed", state_reason="completed")]
    prs = [PrNode(50, "closed", closes=[7])]  # PR fechado sem merge
    fs = closed_but_reverted(issues, prs)
    assert len(fs) == 1 and fs[0].heal == "reopen"


def test_redundant_skeleton_casa_pr_mergeado() -> None:
    # #397 'T1: bracket.ts puro' vs. PR #331 'bracket de torneio puro' mergeado → redundante.
    issues = [IssueNode(397, "T1: bracket.ts puro em packages core", "open", is_auto=True)]
    prs = [PrNode(331, "merged", title="feat(core): bracket de torneio puro seedado")]
    fs = redundant_skeleton(issues, prs)
    assert len(fs) == 1 and fs[0].issue == 397 and fs[0].heal == "close_done"


def test_redundant_skeleton_so_para_auto() -> None:
    # issue normal (não-auto) com título parecido NÃO é flagada (evita fechar trabalho real).
    issues = [IssueNode(50, "bracket de torneio puro", "open", is_auto=False)]
    prs = [PrNode(331, "merged", title="bracket de torneio puro")]
    assert redundant_skeleton(issues, prs) == []


def test_prose_dep_unwired() -> None:
    issues = [IssueNode(286, "scheduler", "open", named_deps=["T1", "T2"])]
    fs = prose_dep_unwired(issues)
    assert len(fs) == 1 and fs[0].kind == "prose_unwired" and fs[0].severity == "aviso"


def test_dependency_cycle_detecta() -> None:
    # A→B→C→A é ciclo; D fora dele não é flagado.
    issues = [
        IssueNode(1, "A", "open", deps=[2]),
        IssueNode(2, "B", "open", deps=[3]),
        IssueNode(3, "C", "open", deps=[1]),
        IssueNode(4, "D", "open", deps=[1]),
    ]
    fs = dependency_cycles(issues)
    assert {f.issue for f in fs} == {1, 2, 3}  # D não entra


def test_sem_ciclo_nao_flaga() -> None:
    issues = [
        IssueNode(1, "A", "open"),
        IssueNode(2, "B", "open", deps=[1]),
        IssueNode(3, "C", "open", deps=[2]),
    ]
    assert dependency_cycles(issues) == []


def test_audit_graph_ordena_erros_antes_de_avisos() -> None:
    issues = [
        IssueNode(286, "scheduler", "closed", deps=[398], state_reason="completed"),  # erro
        IssueNode(398, "T2", "open", named_deps=["algo"]),  # aviso (prose)
    ]
    fs = audit_graph(issues)
    assert fs[0].severity == "erro"  # erro vem primeiro
    assert "closed_dep_open" in _kinds(fs) and "prose_unwired" in _kinds(fs)
