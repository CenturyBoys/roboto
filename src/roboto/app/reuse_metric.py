"""Métrica de REUSO por run (inspirada no `band/metrics.ts` do Ponytail).

Do código NOVO (linhas `+` do diff), quantas CHAMADAS resolvem para símbolos que JÁ existem no repo?
É o KPI "net-new vs reuse" — barato (regex + `git grep` no HEAD), fail-open. Mede se a escada de
decisão ("reuse first") está funcionando POR RUN, não só em benchmark. Puro/injetável → tier-1."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

_CALL = re.compile(r"\b([A-Za-z_]\w{2,})\s*\(")  # `nome(` — uma chamada de função
# início de DEFINIÇÃO: o símbolo DEFINIDO não é uma chamada (ex.: `def novo(` não conta `novo`).
_DEFLINE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function|class|func|interface)\s+\w+")
# nomes genéricos/keywords demais p/ atribuir a UM símbolo do repo (seriam ruído).
_GENERIC = frozenset({
    "if", "for", "while", "return", "print", "len", "str", "int", "dict", "list", "set", "get",
    "init", "map", "filter", "new", "self", "super", "require", "import", "console", "log", "type",
    "range", "tuple", "bool", "float", "object", "parseInt", "parseFloat", "JSON", "Promise",
})

# busca injetável (p/ teste): (workdir, símbolo) -> o símbolo tem definição versionada?
DefSearch = Callable[[str, str], bool]


@dataclass(frozen=True)
class ReuseStat:
    reused: int  # chamadas que resolvem p/ um símbolo JÁ existente no repo
    total: int  # chamadas distintas não-genéricas no código novo

    @property
    def ratio(self) -> float:
        return self.reused / self.total if self.total else 0.0


def _added_lines(diff: str) -> list[str]:
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def _calls(added: list[str]) -> set[str]:
    names: set[str] = set()
    for raw in added:
        ln = _DEFLINE.sub("", raw, count=1)  # tira o símbolo DEFINIDO (não é chamada)
        for m in _CALL.findall(ln):
            if m not in _GENERIC and not m.isupper():  # ignora genéricos e CONSTANTES gritadas
                names.add(m)
    return names


def _git_has_def(workdir: str, sym: str) -> bool:
    pat = rf"(def|function|class|const|interface|type|func)\s+{re.escape(sym)}\b"
    p = subprocess.run(  # noqa: S603,S607 — padrão fixo; sym é identificador escapado
        ["git", "grep", "-lE", pat], cwd=workdir, capture_output=True, text=True, timeout=10,
    )
    return bool(p.stdout.strip())


def reuse_stat(diff: str, workdir: str, *, has_def: DefSearch | None = None) -> ReuseStat:
    """Conta, no código novo do diff, as chamadas que resolvem p/ símbolos já no repo. Fail-open:
    erro na busca de um símbolo não derruba (conta como não-reusado)."""
    search = has_def or _git_has_def
    calls = _calls(_added_lines(diff))
    if not calls:
        return ReuseStat(0, 0)
    reused = 0
    for c in calls:
        try:
            if search(workdir, c):
                reused += 1
        except Exception:  # noqa: BLE001 — best-effort, nunca derruba o ciclo
            pass
    return ReuseStat(reused, len(calls))
