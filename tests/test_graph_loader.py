"""Graph doctor — loader (raw→nós), heal auto-seguro e orquestrador github-backed (épico #73)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.graph_doctor import GraphFinding, plan_heal
from roboto.app.graph_loader import build_nodes, doctor_repo
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

_NOW = datetime(2026, 11, 24, tzinfo=UTC)


def test_build_nodes_mapeia_deps_auto_e_idade() -> None:
    issues = [
        {
            "number": 286, "title": "scheduler", "state": "open",
            "body": "Depende de #398", "labels": [], "created_at": "2026-11-20T00:00:00Z",
        },
        {
            "number": 398, "title": "T2: migration", "state": "open",
            "body": "esqueleto\n- [ ] (a definir no refino)", "labels": [{"name": "auto"}],
            "created_at": "2026-11-10T00:00:00Z",
        },
    ]
    nI, _ = build_nodes(issues, [], now=_NOW)
    by = {i.number: i for i in nI}
    assert by[286].deps == [398]
    assert by[398].is_auto and by[398].refined is False  # esqueleto não-refinado
    assert by[398].age_days == 14  # 24 - 10


def test_build_nodes_detecta_revert_e_closes() -> None:
    prs = [
        {"number": 399, "title": "feat: scheduler", "body": "Closes #286", "merged_at": "x",
         "state": "closed"},
        {"number": 400, "title": "revert: reverter #399", "body": "Reverte o PR #399",
         "merged_at": None, "state": "open"},
    ]
    _, nP = build_nodes([], prs, now=_NOW)
    by = {p.number: p for p in nP}
    assert by[399].state == "merged" and by[399].closes == [286]
    assert by[399].reverted_by == 400  # #400 reverte #399
    assert by[400].state == "open"


def test_plan_heal_so_reabrir_e_auto() -> None:
    fs = [
        GraphFinding("closed_but_reverted", 286, "x", "reopen"),
        GraphFinding("redundant_skeleton", 397, "y", "close_done", "aviso"),
        GraphFinding("prose_unwired", 5, "z", "wire_or_refine", "aviso"),
    ]
    acoes = {a.issue: a for a in plan_heal(fs)}
    assert acoes[286].auto is True and acoes[286].action == "reopen"
    assert acoes[397].auto is False  # fechar redundante exige julgamento (não auto)
    assert acoes[5].auto is False and acoes[5].action == "needs_refine"


class _FakeGh:
    """Github fake p/ o doctor_repo: devolve raw de issues/PRs e grava reaberturas."""

    def __init__(self, issues: list, prs: list) -> None:
        self._issues = issues
        self._prs = prs
        self.reopened: list[int] = []

    async def list_issues_audit(self, repo: str, *, limit: int = 100) -> Result[list, Error]:
        return Ok(self._issues)

    async def list_prs_audit(self, repo: str, *, limit: int = 100) -> Result[list, Error]:
        return Ok(self._prs)

    async def set_issue_state(self, repo: str, n: int, state: str) -> Result[None, Error]:
        if state == "open":
            self.reopened.append(n)
        return Ok(None)


async def test_doctor_repo_reabre_286_automaticamente() -> None:
    # cenário REAL: #286 fechada completa pelo #399 (revertido pelo #400) → doctor REABRE sozinho.
    issues = [
        {"number": 286, "title": "scheduler", "state": "closed", "state_reason": "completed",
         "body": "Depende de #398", "labels": [], "created_at": "2026-11-20T00:00:00Z"},
        {"number": 398, "title": "T2", "state": "open", "body": "x", "labels": [],
         "created_at": "2026-11-20T00:00:00Z"},
    ]
    prs = [
        {"number": 399, "title": "f", "body": "Closes #286", "merged_at": "x", "state": "closed"},
        {"number": 400, "title": "revert: #399", "body": "Reverte #399", "merged_at": None,
         "state": "open"},
    ]
    gh = _FakeGh(issues, prs)
    rep = await doctor_repo(gh, "acme/app", now=_NOW)
    assert isinstance(rep, Ok)
    assert 286 in gh.reopened  # reabriu sozinho (auto-seguro)
    assert any(a.issue == 286 and a.action == "reopen" for a in rep.value.applied)


async def test_doctor_repo_propaga_erro_de_busca() -> None:
    class _Broken(_FakeGh):
        async def list_issues_audit(self, repo: str, *, limit: int = 100) -> Result[list, Error]:
            return Err(Error("github", "boom"))

    rep = await doctor_repo(_Broken([], []), "acme/app", now=_NOW)
    assert isinstance(rep, Err)
