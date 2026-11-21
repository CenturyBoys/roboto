"""Porta de CI local: descobre os scripts do repo e roda-os; vermelho de código × infra."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.repo_ci import CiResult, discover_ci_commands, only_docs_changed, run_ci


def _mk_pkg(tmp_path: Path, scripts: dict[str, str]) -> str:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return str(tmp_path)


def test_discover_ordena_lint_typecheck_test(tmp_path: Path) -> None:
    wd = _mk_pkg(tmp_path, {"test": "turbo test", "lint": "eslint", "typecheck": "tsc --noEmit"})
    cmds = discover_ci_commands(wd)
    assert [n for n, _ in cmds] == ["lint", "typecheck", "test"]  # ordem canônica, não a do json
    assert cmds[0] == ("lint", "pnpm -s lint")


def test_discover_inclui_build_entre_typecheck_e_test(tmp_path: Path) -> None:
    # #117: `build` entra no gate (pega erro que lint/typecheck não veem), ANTES do test.
    wd = _mk_pkg(tmp_path, {"test": "vitest", "build": "next build", "lint": "eslint",
                            "typecheck": "tsc"})
    assert [n for n, _ in discover_ci_commands(wd)] == ["lint", "typecheck", "build", "test"]


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


def test_run_ci_estaticos_rodam_juntos_e_juntam_vermelhos() -> None:
    # lint E typecheck reprovam: a porta roda OS DOIS e devolve um feedback só (1 turno do motor),
    # em vez de parar no lint e precisar de 2 rodadas (mata o ping-pong lint↔typecheck).
    chamados: list[str] = []

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        chamados.append(cmd)
        if "lint" in cmd:
            return 1, "30:15 error Unexpected any @typescript-eslint/no-explicit-any"
        if "typecheck" in cmd:
            return 2, "src/x.ts(2,5): error TS2345: Argument of type 'string'"
        return 0, "ok"

    r = run_ci("/w", [("lint", "pnpm -s lint"), ("typecheck", "pnpm -s typecheck")], runner=runner)
    assert r.passed is False
    assert r.which == "lint, typecheck"  # os dois vermelhos reportados juntos
    assert r.fixable is True  # erro de código → o motor pode corrigir
    assert "no-explicit-any" in r.red and "TS2345" in r.red  # ambos os vermelhos no feedback
    assert chamados == ["pnpm -s lint", "pnpm -s typecheck"]  # rodou os DOIS estáticos


def test_run_ci_estatico_so_um_vermelho_reporta_so_ele() -> None:
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        if "lint" in cmd:
            return 1, "30:15 error Unexpected any @typescript-eslint/no-explicit-any"
        return 0, "ok"  # typecheck verde

    r = run_ci("/w", [("lint", "pnpm -s lint"), ("typecheck", "pnpm -s typecheck")], runner=runner)
    assert r.which == "lint" and r.fixable is True
    assert "no-explicit-any" in r.red


def test_run_ci_estaticos_verdes_so_entao_roda_test() -> None:
    # `test` é fase de serviço: só roda DEPOIS que lint/typecheck estão verdes (barato→caro).
    chamados: list[str] = []

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        chamados.append(cmd)
        if "lint" in cmd:
            return 1, "error no-explicit-any"  # estático vermelho → nem chega no test
        return 0, "ok"

    cmds = [("lint", "pnpm -s lint"), ("typecheck", "pnpm -s typecheck"), ("test", "pnpm -s test")]
    run_ci("/w", cmds, runner=runner)
    # estático vermelho segura o test (não desperdiça a suíte lenta com lint/type ainda vermelhos)
    assert "pnpm -s test" not in chamados


def test_run_ci_build_erro_de_codigo_e_fixable() -> None:
    # #117: erro REAL de build (Next detecta middleware.ts + proxy.ts juntos) é CÓDIGO → realimenta.
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        if "build" in cmd:
            return 1, 'Both middleware file "./src/middleware.ts" and proxy file "./src/proxy.ts"'
        return 0, "ok"

    r = run_ci("/w", [("build", "pnpm -s build")], runner=runner)
    assert r.which == "build" and r.infra is False and r.fixable is True  # volta ao motor


def test_run_ci_build_erro_de_infra_nao_e_fixable() -> None:
    # build que cai por serviço/env (ECONNREFUSED) é INFRA → surfa, não culpa o modelo.
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "Error: connect ECONNREFUSED 127.0.0.1:5432 durante o build"

    r = run_ci("/w", [("build", "pnpm -s build")], runner=runner)
    assert r.infra is True and r.fixable is False


def test_run_ci_build_roda_antes_do_test() -> None:
    # build vermelho segura o test (compila antes de testar): estáticos verdes → build → para.
    chamados: list[str] = []

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        chamados.append(cmd)
        return (1, "Build error") if "build" in cmd else (0, "ok")

    cmds = [("typecheck", "pnpm -s tc"), ("build", "pnpm -s build"), ("test", "pnpm -s test")]
    r = run_ci("/w", cmds, runner=runner)
    assert r.which == "build"
    assert "pnpm -s test" not in chamados  # build quebrou → nem roda o test


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


# --- RESILIÊNCIA: se o `test` reprova por ambiente E temos setup, SOBE o ambiente e RE-RODA ---

_SETUP = (("db:generate", "pnpm -s db:generate"), ("db:migrate", "pnpm -s db:migrate"))


def test_run_ci_sobe_ambiente_e_fica_verde() -> None:
    # test 1ª vez = DB não migrado (infra); roda o setup; re-roda → verde (validado DE VERDADE).
    calls: list[str] = []

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        calls.append(cmd)
        if "db:" in cmd:
            return 0, "migrated"
        n_test = sum(1 for c in calls if c.endswith("test"))
        if n_test == 1:
            return 1, "The table public.account does not exist (code P2021)"
        return 0, "all tests passed"

    r = run_ci("/w", [("test", "pnpm -s test")], setup=_SETUP, runner=runner)
    assert r.passed is True  # subiu o ambiente e o teste passou de verdade
    assert r.prepared is True
    assert any("db:migrate" in c for c in calls)  # rodou o setup do repo


def test_run_ci_sobe_ambiente_e_revela_erro_real_fixable() -> None:
    # O GANHO: o 1º vermelho PARECIA infra ("table does not exist"); subimos o ambiente e o re-run
    # falhou com erro de CÓDIGO → re-classificado FIXABLE (realimenta o motor). Antes: mascarado.
    calls: list[str] = []

    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        calls.append(cmd)
        if "db:" in cmd:
            return 0, "ok"
        n_test = sum(1 for c in calls if c.endswith("test"))
        if n_test == 1:
            return 1, "relation \"games\" does not exist"  # cara de infra
        return 1, "AssertionError: expected 2 to equal 3"  # erro REAL, pós-ambiente

    r = run_ci("/w", [("test", "pnpm -s test")], setup=_SETUP, runner=runner)
    assert r.passed is False
    assert r.infra is False  # re-classificado pela saída REAL do re-run
    assert r.fixable is True  # AGORA volta ao motor (antes ficava mascarado como infra)
    assert r.prepared is True


def test_run_ci_sobe_ambiente_mas_segue_infra_honesto() -> None:
    # serviço genuinamente ausente: nem subindo resolve → infra HONESTO, com os services nomeados.
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "Error: connect ECONNREFUSED 127.0.0.1:5432"

    r = run_ci(
        "/w", [("test", "pnpm -s test")], setup=_SETUP,
        services=("postgres", "redis"), runner=runner,
    )
    assert r.passed is False
    assert r.infra is True
    assert r.prepared is True  # tentamos subir
    assert r.fixable is False
    assert r.services == ("postgres", "redis")  # p/ a mensagem honesta


def test_run_ci_sem_setup_mantem_comportamento_antigo() -> None:
    # sem setup (repo sem scripts de ambiente) → infra segue infra, SEM tentar preparar (compat).
    def runner(cmd: str, cwd: str, timeout: float) -> tuple[int, str]:
        return 1, "The table public.account does not exist (P2021)"

    r = run_ci("/w", [("test", "pnpm -s test")], runner=runner)
    assert r.infra is True
    assert r.prepared is False  # não havia como subir o ambiente → não tentou


def test_only_docs_changed() -> None:
    assert only_docs_changed(["docs/x.md", "README.md"]) is True
    assert only_docs_changed(["docs/arch/view.md", "CHANGELOG"]) is True
    assert only_docs_changed(["src/app.ts", "docs/x.md"]) is False  # tem código → precisa testar
    assert only_docs_changed([".github/workflows/ci.yml"]) is False  # workflow não é doc
    assert only_docs_changed([]) is False  # vazio: não afirma
