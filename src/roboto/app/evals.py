"""Evals determinísticos das funções de decisão de segurança (Trilha H).

Golden set versionado (`evals/golden/*.json`) de casos `input → expect` rodados como **gate de CI**:
regressão numa das decisões DETERMINÍSTICAS do fleet barra o merge. Sem LLM aqui (sem custo/flaky no
CI) — os evals de LLM-as-judge (dimensões subjetivas: qualidade de refino/review) ficam como
follow-up AGENDADO, não contínuo (senão não dá pra separar regressão do agente de drift do dataset).

Cobre os graders que SÃO a camada de segurança (determinismo primeiro): prontidão (DoR),
classificação de task, risk-tiering (jev-guard) e secret-scan. O golden cresce com FALHAS REAIS —
cada caso que escapou vira um caso aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import check_issue_readiness
from roboto.app.jev_guard import assess as assess_risk
from roboto.app.secret_scan import scan_diff
from roboto.app.task_class import classificar_task

GRADERS = ("dor", "task_class", "risk", "secret")


@dataclass(frozen=True)
class EvalCase:
    id: str
    grader: str
    input: dict[str, object]
    expect: dict[str, object]


@dataclass(frozen=True)
class EvalResult:
    id: str
    grader: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class EvalReport:
    total: int
    passed: int
    failures: list[EvalResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


def _grade_dor(inp: dict[str, object], expect: dict[str, object]) -> tuple[bool, str]:
    verdict = check_issue_readiness(
        IssueDraft(title=str(inp.get("title", "")), body=str(inp.get("body", "")))
    )
    want = bool(expect.get("ready"))
    return verdict.ready == want, f"ready={verdict.ready} (esp {want}); falta={verdict.missing}"


def _grade_task_class(inp: dict[str, object], expect: dict[str, object]) -> tuple[bool, str]:
    tc = classificar_task(str(inp.get("title", "")), str(inp.get("body", "")))
    want = str(expect.get("task_type", ""))
    return str(tc.task_type) == want, f"task_type={tc.task_type} (esperado {want})"


def _grade_risk(inp: dict[str, object], expect: dict[str, object]) -> tuple[bool, str]:
    raw = inp.get("files", [])
    files = [str(f) for f in raw] if isinstance(raw, list) else []
    risk = assess_risk(files)
    want = str(expect.get("level", ""))
    return risk.level == want, f"level={risk.level} (esperado {want})"


def _grade_secret(inp: dict[str, object], expect: dict[str, object]) -> tuple[bool, str]:
    found = bool(scan_diff(str(inp.get("diff", ""))))
    want = bool(expect.get("has_secret"))
    return found == want, f"has_secret={found} (esperado {want})"


_DISPATCH = {
    "dor": _grade_dor,
    "task_class": _grade_task_class,
    "risk": _grade_risk,
    "secret": _grade_secret,
}


def grade(case: EvalCase) -> EvalResult:
    fn = _DISPATCH.get(case.grader)
    if fn is None:
        return EvalResult(case.id, case.grader, False, f"grader desconhecido: {case.grader}")
    passed, detail = fn(case.input, case.expect)
    return EvalResult(case.id, case.grader, passed, detail)


def run_evals(cases: list[EvalCase]) -> EvalReport:
    results = [grade(c) for c in cases]
    failures = [r for r in results if not r.passed]
    return EvalReport(total=len(results), passed=len(results) - len(failures), failures=failures)


def cases_from_json(data: list[dict[str, object]]) -> list[EvalCase]:
    """Converte o JSON do golden set em `EvalCase` (tolera campos faltando com defaults vazios)."""
    cases: list[EvalCase] = []
    for d in data:
        inp = d.get("input", {})
        exp = d.get("expect", {})
        cases.append(
            EvalCase(
                id=str(d.get("id", "")),
                grader=str(d.get("grader", "")),
                input=inp if isinstance(inp, dict) else {},
                expect=exp if isinstance(exp, dict) else {},
            )
        )
    return cases
