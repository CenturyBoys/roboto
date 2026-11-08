"""Porta de CI local: descobre os scripts do repo e roda-os; vermelho de código × infra."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.repo_ci import CiResult, discover_ci_commands, run_ci


def _mk_pkg(tmp_path: Path, scripts: dict[str, str]) -> str:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return str(tmp_path)


def test_discover_ordena_lint_typecheck_test(tmp_path: Path) -> None:
    wd = _mk_pkg(tmp_path, {"test": "turbo test", "lint": "eslint", "typecheck": "tsc --noEmit"})
    cmds = discover_ci_commands(wd)
    assert [n for n, _ in cmds] == ["lint", "typecheck", "test"]  # ordem canônica, não a do json
    assert cmds[0] == ("lint", "pnpm -s lint")


def test_discover_so_os_que_existem(tmp_path: Path) -> None:
    wd = _mk_pkg(tmp_path, {"lint": "eslint"})  # só lint
    assert discover_ci_commands(wd) == [("lint", "pnpm -s lint")]


def test_discover_override_filtra(tmp_path: Path) -> None:
    wd = _mk_pkg(tmp_path, {"lint": "eslint", "typecheck": "tsc", "test": "vitest"})
    got = [n for n, _ in discover_ci_commands(wd, override="typecheck,lint")]
    assert got == ["typecheck", "lint"]


def test_discover_sem_package_json_vazio(tmp_path: Path) -> None:
    assert discover_ci_commands(str(tmp_path)) == []  # porta vira no-op


def test_run_ci_tudo_verde() -> None:
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 0, "ok"

    r = run_ci("/w", [("lint", "pnpm -s lint"), ("test", "pnpm -s test")], runner=runner)
    assert r == CiResult(True)


def test_run_ci_para_no_primeiro_vermelho() -> None:
    chamados: list[str] = []

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        chamados.append(cmd)
        if "lint" in cmd:
            return 1, "30:15 error Unexpected any @typescript-eslint/no-explicit-any"
        return 0, "ok"

    r = run_ci("/w", [("lint", "pnpm -s lint"), ("typecheck", "pnpm -s typecheck")], runner=runner)
    assert r.passed is False
    assert r.which == "lint"
    assert r.fixable is True  # erro de código → o motor pode corrigir
    assert "no-explicit-any" in r.red
    assert chamados == ["pnpm -s lint"]  # parou no 1º vermelho (não rodou typecheck)


def test_run_ci_vermelho_de_infra_nao_e_fixable() -> None:
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "Error: connect ECONNREFUSED 127.0.0.1:5432 (database)"

    r = run_ci("/w", [("test", "pnpm -s test")], runner=runner)
    assert r.passed is False
    assert r.infra is True
    assert r.fixable is False  # infra: não realimenta o motor


def test_run_ci_banco_de_teste_nao_migrado_e_infra() -> None:
    # caso real (run #103): teste de integração sem DB migrado → infra, não culpa do modelo.
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, (
            "PrismaClientKnownRequestError: \n"
            "Invalid `prisma.account.findMany()` invocation\n"
            "The table `public.account` does not exist in the current database. (code P2021)"
        )

    r = run_ci("/w", [("test", "pnpm -s test")], runner=runner)
    assert r.passed is False
    assert r.infra is True  # banco de teste não provisionado localmente
    assert r.fixable is False  # não realimenta o motor (3 turnos à toa no #103)


def test_run_ci_typecheck_cannot_find_module_e_codigo_nao_infra() -> None:
    # regressão do run #104: TS2307 `Cannot find module` no TYPECHECK é código (import errado),
    # não infra — tem de voltar ao motor; waved-through reabre PR vermelho.
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 2, "src/lib/versioning.test.ts(2,56): error TS2307: Cannot find module '../check'"

    r = run_ci("/w", [("typecheck", "pnpm -s typecheck")], runner=runner)
    assert r.passed is False
    assert r.infra is False  # typecheck não é passo de infra
    assert r.fixable is True  # volta ao motor


def test_run_ci_lint_nunca_e_infra() -> None:
    # mesmo um texto com cara de infra no LINT conta como código (lint é estático puro).
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "Cannot find module 'x' / ECONNREFUSED (ruído)"

    r = run_ci("/w", [("lint", "pnpm -s lint")], runner=runner)
    assert r.infra is False and r.fixable is True


def test_run_ci_timeout_vira_infra() -> None:
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        raise TimeoutError("estourou")

    r = run_ci("/w", [("test", "pnpm -s test")], runner=runner)
    assert r.infra is True and r.fixable is False


def test_run_ci_trima_saida_pelo_fim() -> None:
    cauda = "ERRO REAL no fim"

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, ("barulho " * 2000) + cauda

    r = run_ci("/w", [("lint", "x")], runner=runner, max_red_chars=50)
    assert len(r.red) <= 50
    assert r.red.endswith(cauda)
