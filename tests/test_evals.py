"""Evals determinísticos (Trilha H): runner + golden set versionado."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.evals import EvalCase, cases_from_json, grade, run_evals

_GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"


def test_grade_dor_ready() -> None:
    body = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] z\n## DoD\n- [ ] ci"
    case = EvalCase(
        id="x", grader="dor", input={"title": "t", "body": body}, expect={"ready": True}
    )
    assert grade(case).passed


def test_grade_risk_high() -> None:
    case = EvalCase(
        id="r", grader="risk", input={"files": ["db/migrations/1.sql"]}, expect={"level": "alto"}
    )
    assert grade(case).passed


def test_grade_secret_detects() -> None:
    case = EvalCase(
        id="s", grader="secret",
        input={"diff": "+k = \"ghp_" + "a" * 36 + "\""}, expect={"has_secret": True},
    )
    assert grade(case).passed


def test_unknown_grader_fails_gracefully() -> None:
    assert grade(EvalCase(id="u", grader="nope", input={}, expect={})).passed is False


def test_report_counts_failures() -> None:
    cases = [
        EvalCase(id="ok", grader="risk", input={"files": ["a.py"]}, expect={"level": "baixo"}),
        EvalCase(id="bad", grader="risk", input={"files": ["a.py"]}, expect={"level": "alto"}),
    ]
    report = run_evals(cases)
    assert report.total == 2 and report.passed == 1 and not report.ok
    assert report.failures[0].id == "bad"


def test_golden_set_all_pass() -> None:
    # o golden set versionado DEVE passar — é o baseline do gate de CI.
    cases = []
    for f in sorted(_GOLDEN.glob("*.json")):
        cases += cases_from_json(json.loads(f.read_text()))
    assert cases, "golden set vazio"
    report = run_evals(cases)
    assert report.ok, f"golden falhou: {[(r.id, r.detail) for r in report.failures]}"
