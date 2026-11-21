"""Mapa determinístico do repo-alvo, injetado no início do impl (inspirado no `ponytail-map`).

Materializa o degrau "já existe neste repo? reuse" da escada de decisão (ver prompt do impl) SEM
gastar token de busca nem depender do modelo escolher buscar — determinismo 1º, harness-driven
(casa com [[code-intel-harness-driven]]). Puro: `git ls-files` + regex por linguagem → 1 linha por
diretório com símbolos top-level, priorizando pastas COMPARTILHADAS (util/lib/service/...), dentro
de um budget de chars. Fail-open: qualquer erro → mapa vazio (nunca derruba o run)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

# símbolo top-level por extensão (o que é exportado/definido no nível do arquivo).
_PY = re.compile(r"^(?:async def|def|class)\s+([A-Za-z_]\w*)", re.M)
_TS = re.compile(
    r"^export\s+(?:async\s+)?(?:function|class|const|interface|type|enum)\s+([A-Za-z_]\w*)", re.M
)
_GO = re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Z]\w*)", re.M)
_LANG: dict[str, re.Pattern[str]] = {
    ".py": _PY, ".ts": _TS, ".tsx": _TS, ".js": _TS, ".jsx": _TS, ".mjs": _TS, ".go": _GO,
}
# pastas onde mais se reusa → vêm PRIMEIRO no mapa (prioriza o budget nelas).
_SHARED = re.compile(r"util|lib|service|component|hook|helper|shared|core|common", re.I)

# runner injetável (p/ teste): workdir -> lista de paths relativos versionados.
Lister = Callable[[str], list[str]]


def _git_ls(workdir: str) -> list[str]:
    p = subprocess.run(  # noqa: S603,S607 — comando fixo, não input do modelo
        ["git", "ls-files"], cwd=workdir, capture_output=True, text=True, timeout=10,
    )
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def build_codebase_map(workdir: str, *, budget: int = 2000, lister: Lister | None = None) -> str:
    """Mapa do repo: 1 linha por diretório `path: sym1, sym2, …`, compartilhadas primeiro, capado
    pelo `budget`. Vazio se não houver símbolos ou em qualquer erro (fail-open)."""
    run = lister or _git_ls
    try:
        files = run(workdir)
    except Exception:  # noqa: BLE001 — sem git/listagem → sem mapa (degrada normal)
        return ""
    by_dir: dict[str, set[str]] = {}
    for rel in files:
        rx = _LANG.get(Path(rel).suffix)
        if rx is None:
            continue
        try:
            text = (Path(workdir) / rel).read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001 — arquivo ilegível → pula
            continue
        syms = rx.findall(text)
        if syms:
            by_dir.setdefault(str(Path(rel).parent), set()).update(syms[:40])
    if not by_dir:
        return ""
    dirs = sorted(by_dir, key=lambda d: (0 if _SHARED.search(d) else 1, d))
    linhas: list[str] = []
    total = 0
    for i, d in enumerate(dirs):
        linha = f"{d}: {', '.join(sorted(by_dir[d])[:12])}"
        if total + len(linha) > budget:
            linhas.append(f"… (+{len(dirs) - i} diretórios omitidos pelo budget)")
            break
        linhas.append(linha)
        total += len(linha) + 1
    return (
        "MAPA DO REPO (o que JÁ existe — reuse; só leia um arquivo se precisar do detalhe):\n"
        + "\n".join(linhas)
    )
