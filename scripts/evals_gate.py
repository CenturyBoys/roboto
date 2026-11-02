#!/usr/bin/env python3
"""Gate de evals (Trilha H): roda o golden set determinístico e falha (exit 1) em regressão.

Carrega todos os `evals/golden/*.json`, roda os graders e imprime um relatório. Usado no CI como
gate anti-regressão das decisões de segurança (DoR, task_class, risco, secret-scan). Sem LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from roboto.app.evals import cases_from_json, run_evals

_GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"


def main() -> int:
    files = sorted(_GOLDEN.glob("*.json"))
    if not files:
        print(f"nenhum golden set em {_GOLDEN}")
        return 1
    cases = []
    for f in files:
        cases += cases_from_json(json.loads(f.read_text()))
    report = run_evals(cases)
    print(f"evals: {report.passed}/{report.total} ok ({len(files)} arquivo(s) golden)")
    for fail in report.failures:
        print(f"  ✗ [{fail.grader}] {fail.id}: {fail.detail}")
    if not report.ok:
        print(f"REGRESSÃO: {len(report.failures)} caso(s) falharam — gate bloqueado.")
        return 1
    print("gate verde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
