#!/usr/bin/env python3
"""Doc-in-sync guard (AGENTS §5): PR que muda código de DOMÍNIO sem tocar a doc -> falha.

Determinístico, barato, bloqueante no CI. Escape consciente: `[skip-docs]` no título do PR (ou na
env `PR_TITLE`) quando a mudança realmente não pede doc (ex.: refactor interno puro).

Uso:
    python scripts/doc_guard.py [<base_ref>]   # default: origin/main
"""

from __future__ import annotations

import os
import subprocess
import sys

CODE_PREFIX = "src/roboto/"
DOC_HINTS = ("docs/", "research/", "README.md", "AGENTS.md")


def _changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _is_domain_code(path: str) -> bool:
    if not path.startswith(CODE_PREFIX) or not path.endswith(".py"):
        return False
    nome = path.rsplit("/", 1)[-1]
    return not nome.startswith("test_")  # testes não exigem doc


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    files = _changed_files(base)
    code = [f for f in files if _is_domain_code(f)]
    doc_touched = any(f.startswith(DOC_HINTS) or f.endswith(".md") for f in files)

    if "[skip-docs]" in os.environ.get("PR_TITLE", ""):
        print("doc-guard: pulado ([skip-docs] no título).")
        return 0
    if code and not doc_touched:
        print("❌ doc-guard: mudou código de domínio SEM tocar documentação:")
        for f in code:
            print(f"   - {f}")
        print(
            "\nAtualize `docs/` (ou research/AGENTS/README) no MESMO PR — doc-in-sync (AGENTS §5).\n"
            "Se realmente não precisa de doc, ponha `[skip-docs]` no título do PR."
        )
        return 1
    print("✅ doc-guard: ok.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
