"""Porta de CI LOCAL (determinismo 1º): roda a MESMA verificação do CI do repo-alvo
(lint/typecheck/test) ANTES do push — p/ o fleet não abrir PR que o CI vai reprovar.

Aprendizado (2026-11-08): o fleet abria PR sem rodar o `pnpm lint/typecheck/test` do repo; o CI
reprovava no lint (`no-explicit-any`) e isso chegava INVISÍVEL ao operador — só "failed" seco. A
porta descobre os scripts reais do `package.json` e roda-os; vermelho de CÓDIGO volta ao motor como
feedback autoritativo; vermelho de INFRA (DB fora, deps faltando) degrada p/ "indisponível" (não
trava, não culpa o modelo — o CI do GitHub segue juiz final). I/O injetável (`runner`) → tier-1.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# ordem canônica barato→caro: lint e typecheck não precisam de infra; `test` pode precisar (DB).
_CANON_ORDER = ("lint", "typecheck", "test")

# passos que PODEM reprovar por infra (precisam de DB/serviços). lint/typecheck são análise estática
# PURA — qualquer vermelho ali é CÓDIGO (ex.: TS2307 `Cannot find module` = import errado), nunca
# infra; waved-through ali reabre PR vermelho (run #104). Só o `test` ganha o benefício da dúvida.
_INFRA_CAPABLE = {"test"}

# padrões de vermelho que são de INFRA/ambiente (não a mudança do modelo) → NÃO realimenta o motor.
# Inclui banco de teste não provisionado (ex.: integração Prisma sem migração): o CI do GitHub roda
# com DB migrado, é o juiz desses — localmente degrada p/ "indisponível", não trava nem escala.
_INFRA_RED = re.compile(
    r"ECONNREFUSED|could not connect|getaddrinfo|ENOTFOUND|connection refused|"
    r"database .{0,60}does not exist|role .{0,60}does not exist|password authentication|"
    r"Cannot find module|command not found|ENOENT|No such file|corepack|pnpm: not found|"
    # banco de teste não migrado (Prisma/SQL): tabela/relação ausente, código P2021, conexão
    r"table .{0,60}does not exist|relation .{0,60}does not exist|"
    r"PrismaClient\w*Error|P2021|P10\d\d|prisma migrate|needs? to be migrated|not migrated",
    re.I,
)

# runner: (cmd, cwd, timeout) -> (returncode, saída combinada). Injetável p/ teste.
Runner = Callable[[str, str, float], tuple[int, str]]


@dataclass(frozen=True)
class CiResult:
    passed: bool
    which: str = ""  # nome do check que reprovou (lint/typecheck/test)
    red: str = ""  # saída trimada do vermelho (alimenta o motor)
    infra: bool = False  # vermelho parece INFRA → não realimenta o motor, só surfa

    @property
    def fixable(self) -> bool:
        """Vermelho que o motor PODE corrigir (erro de código, não de infra)."""
        return not self.passed and not self.infra


def discover_ci_commands(workdir: str, *, override: str = "") -> list[tuple[str, str]]:
    """Scripts de check do repo (`package.json` da raiz), na ordem lint→typecheck→test, como
    `pnpm -s <script>` (= o que o CI roda via turbo). `override` (env `ROBOTO_LOCAL_CI_CMDS`,
    ex.: "lint,typecheck") filtra/ordena por nome. Sem package.json legível ou sem os scripts →
    lista vazia (porta vira no-op e o ciclo degrada normal)."""
    sel = [s.strip() for s in override.split(",") if s.strip()] if override else list(_CANON_ORDER)
    try:
        pkg = json.loads((Path(workdir) / "package.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — sem package.json legível → nada a rodar
        return []
    scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
    return [(name, f"pnpm -s {name}") for name in sel if name in scripts]


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _default_runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
    # cmd é um script do package.json (config do repo), não input do modelo — shell p/ casar o CI.
    p = subprocess.run(  # noqa: S602
        cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, _strip_ansi((p.stdout or "") + "\n" + (p.stderr or ""))


def run_ci(
    workdir: str,
    commands: list[tuple[str, str]],
    *,
    runner: Runner | None = None,
    timeout: float = 300.0,
    max_red_chars: int = 3000,
) -> CiResult:
    """Roda os checks em sequência, parando no 1º vermelho. SÍNCRONO (use `asyncio.to_thread`).
    Nunca levanta: timeout/execução vira `CiResult(infra=True)`. Vazio/tudo-verde → `passed=True`.
    A saída do vermelho é trimada pelo FIM (onde o erro real aparece) p/ caber no prompt."""
    run = runner or _default_runner
    for name, cmd in commands:
        try:
            rc, saida = run(cmd, workdir, timeout)
        except Exception as exc:  # noqa: BLE001 — timeout/exec → trata como infra (não culpa modelo)
            return CiResult(
                False, which=name, red=f"{type(exc).__name__}: {exc}"[:max_red_chars], infra=True
            )
        if rc != 0:
            red = saida.strip()[-max_red_chars:]
            # infra só vale p/ passos que tocam serviços (test); lint/typecheck vermelho = código.
            infra = name in _INFRA_CAPABLE and bool(_INFRA_RED.search(saida))
            return CiResult(False, which=name, red=red, infra=infra)
    return CiResult(True)
