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
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# ordem canônica barato→caro: lint/typecheck (estática pura) → `build` (compila: pega erro que o
# typecheck não vê, ex.: Next `middleware.ts`+`proxy.ts` juntos = build quebra, run #117) → `test`
# (pode precisar de DB). build roda ANTES do test: sem compilar, nem adianta testar.
_CANON_ORDER = ("lint", "typecheck", "build", "test")

# passos que PODEM reprovar por infra (precisam de serviço/env). lint/typecheck são análise estática
# PURA — qualquer vermelho ali é CÓDIGO (ex.: TS2307 `Cannot find module` = import errado), nunca
# infra; waved-through ali reabre PR vermelho (run #104). `test` e `build` ganham o benefício da
# dúvida (build pode faltar env/serviço); o erro de CÓDIGO (não casa `_INFRA_RED`) ainda realimenta.
_INFRA_CAPABLE = {"test", "build"}

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
    prepared: bool = False  # tentamos SUBIR o ambiente (setup do repo) e re-rodar antes de julgar
    services: tuple[str, ...] = ()  # serviços que o CI do alvo exige (p/ mensagem honesta)

    @property
    def fixable(self) -> bool:
        """Vermelho que o motor PODE corrigir (erro de código, não de infra)."""
        return not self.passed and not self.infra


# arquivos que são DOCUMENTAÇÃO: não exigem build/test de serviço (nem subir postgres/redis).
_DOC_FILE = re.compile(
    r"(^|/)(docs?/)|(^|/)(readme|changelog|contributing)|\.(mdx?|rst|txt|adoc)$", re.I
)


def only_docs_changed(files: list[str]) -> bool:
    """True se TODO arquivo mudado é documentação → o run NÃO precisa de build/test (nem de subir
    os serviços do CI). Vazio → False (não dá pra afirmar). Base p/ provisionar recurso só quando
    a task REALMENTE roda teste (não gastar postgres/redis num PR só-doc)."""
    real = [f for f in files if f and f != "/dev/null"]
    return bool(real) and all(_DOC_FILE.search(f) for f in real)


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


def _make_default_runner(env: dict[str, str] | None) -> Runner:
    """Runner de subprocess com o `env` do CI do alvo aplicado (DATABASE_URL/REDIS_URL…) por cima
    do os.environ. `env` vazio/None → ambiente do processo (comportamento antigo)."""
    full_env = {**os.environ, **env} if env else None

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        # cmd é script do package.json (config do repo), não input do modelo — shell p/ casar o CI.
        p = subprocess.run(  # noqa: S602
            cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout, env=full_env,
        )
        return p.returncode, _strip_ansi((p.stdout or "") + "\n" + (p.stderr or ""))

    return runner


def run_ci(
    workdir: str,
    commands: list[tuple[str, str]],
    *,
    setup: tuple[tuple[str, str], ...] = (),
    env: dict[str, str] | None = None,
    services: tuple[str, ...] = (),
    runner: Runner | None = None,
    timeout: float = 300.0,
    max_red_chars: int = 3000,
) -> CiResult:
    """Roda os checks e devolve o 1º bloco acionável de vermelho. SÍNCRONO (`asyncio.to_thread`).
    Nunca levanta: timeout/execução vira `CiResult(infra=True)`. Vazio/tudo-verde → `passed=True`.

    Fase ESTÁTICA (lint/typecheck): análise pura, sem infra. Roda TODOS e junta os vermelhos num
    feedback só — o motor corrige lint+typecheck de UMA vez (1 turno), não um turno por check (mata
    o ping-pong "arruma lint → quebra typecheck"). Fase de SERVIÇO (`test`): barato→caro, para no
    1º vermelho.

    RESILIÊNCIA (determinismo 1º): em vez de chutar "infra" e pular, se o `test` reprova com cara de
    ambiente E temos `setup` (do CI do alvo, ver `target_env`), SOBE o ambiente (roda o setup com o
    `env` do CI) e RE-RODA o teste UMA vez — o resultado REAL decide: verde = validado de verdade;
    vermelho de CÓDIGO = realimenta o motor (`fixable`); só degrada p/ `infra` (honesto, nomeando os
    `services`) se nem subindo resolver. Cada vermelho é trimado pelo FIM p/ caber no prompt."""
    run = runner or _make_default_runner(env)

    def executar(name: str, cmd: str) -> tuple[int, str] | CiResult:
        # exceção (timeout/exec não-iniciado) = ambiente, não a mudança do modelo → infra.
        try:
            return run(cmd, workdir, timeout)
        except Exception as exc:  # noqa: BLE001
            return CiResult(
                False, which=name, red=f"{type(exc).__name__}: {exc}"[:max_red_chars], infra=True
            )

    # FASE 1 — checks estáticos juntos: acumula TODOS os vermelhos (código, nunca infra).
    vermelhos_estaticos: list[tuple[str, str]] = []  # (check, saída trimada pelo fim)
    for name, cmd in ((n, c) for n, c in commands if n not in _INFRA_CAPABLE):
        resultado = executar(name, cmd)
        if isinstance(resultado, CiResult):
            return resultado  # exceção num check estático → infra (sai sem acumular)
        rc, saida = resultado
        if rc != 0:
            vermelhos_estaticos.append((name, saida.strip()[-max_red_chars:]))
    if vermelhos_estaticos:
        # 1 vermelho: saída crua (preserva o orçamento por check). 2+: delimita com `== check ==`
        # p/ o motor saber qual erro é de qual check e corrigir os dois no mesmo turno.
        which = ", ".join(name for name, _ in vermelhos_estaticos)
        red = (
            vermelhos_estaticos[0][1]
            if len(vermelhos_estaticos) == 1
            else "\n\n".join(f"== {name} ==\n{red}" for name, red in vermelhos_estaticos)
        )
        return CiResult(False, which=which, red=red)

    # FASE 2 — checks que tocam serviços (`test`): estáticos já verdes; para no 1º vermelho.
    prepared = False
    for name, cmd in ((n, c) for n, c in commands if n in _INFRA_CAPABLE):
        resultado = executar(name, cmd)
        if isinstance(resultado, CiResult):
            return resultado
        rc, saida = resultado
        if rc == 0:
            continue
        infra = bool(_INFRA_RED.search(saida))
        # RESILIÊNCIA: vermelho com cara de ambiente + temos setup + ainda não preparamos → SOBE o
        # ambiente (migrate/generate do próprio repo) e RE-RODA uma vez; a realidade decide.
        if infra and setup and not prepared:
            prepared = True
            for sname, scmd in setup:
                executar(sname, scmd)  # best-effort, idempotente (ignora retorno/exceção)
            rerun = executar(name, cmd)
            if isinstance(rerun, CiResult):  # exceção no re-run → infra (ainda indisponível)
                return CiResult(False, which=name, red=rerun.red, infra=True,
                                prepared=True, services=services)
            rc, saida = rerun
            if rc == 0:
                continue  # ambiente subiu, teste passou DE VERDADE
            infra = bool(_INFRA_RED.search(saida))  # re-classifica pela saída REAL do re-run
        return CiResult(
            False, which=name, red=saida.strip()[-max_red_chars:],
            infra=infra, prepared=prepared, services=services,
        )
    # verde: propaga `prepared` — se subimos o ambiente e o teste passou, é sinal POSITIVO (validado
    # de verdade, não pulado), que o ciclo pode surfar ("subi o ambiente e o test passou ✅").
    return CiResult(True, prepared=prepared)
