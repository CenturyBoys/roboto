"""Leitura do CI do repo-alvo p/ subir o ambiente de teste (env/services/setup). Parser puro."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.target_env import discover_setup_commands, parse_ci_env, read_target_env

# recorte do ci.yml real do jo-ken-po (services postgres/redis + env + steps de setup).
_CI_YML = """
name: CI
on: [pull_request]
jobs:
  verify:
    runs-on: [self-hosted]
    services:
      postgres:
        image: postgres:18
        ports: ["5432:5432"]
      redis:
        image: redis:8
    env:
      DATABASE_URL: postgresql://jokenpo:jokenpo@localhost:5432/jokenpo_test?schema=public
      REDIS_URL: redis://localhost:6379
      SECRET: ${{ secrets.TOKEN }}
    steps:
      - run: pnpm --filter @jo-ken-po/db db:migrate
"""


def test_parse_ci_env_pega_env_e_services() -> None:
    env, services = parse_ci_env(_CI_YML)
    assert env["DATABASE_URL"].endswith("jokenpo_test?schema=public")
    assert env["REDIS_URL"] == "redis://localhost:6379"
    assert services == ("postgres", "redis")


def test_parse_ci_env_ignora_valores_dinamicos() -> None:
    env, _ = parse_ci_env(_CI_YML)
    assert "SECRET" not in env  # ${{ secrets.* }} não resolve localmente → descartado


def test_parse_ci_env_yaml_invalido_degrada() -> None:
    env, services = parse_ci_env(": : : não é yaml válido : [")
    assert env == {} and services == ()


def test_discover_setup_commands_ordem_canonica(tmp_path: Path) -> None:
    # generate antes de migrate; ignora scripts que não são de setup (lint/test).
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {
            "db:migrate": "turbo run db:migrate",
            "db:generate": "turbo run db:generate",
            "test": "turbo run test",
            "lint": "x",
        }}),
        encoding="utf-8",
    )
    cmds = discover_setup_commands(str(tmp_path))
    assert cmds == (("db:generate", "pnpm -s db:generate"), ("db:migrate", "pnpm -s db:migrate"))


def test_discover_setup_commands_sem_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}), encoding="utf-8")
    assert discover_setup_commands(str(tmp_path)) == ()


def test_read_target_env_junta_ci_e_package(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(_CI_YML, encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"db:migrate": "turbo run db:migrate"}}), encoding="utf-8"
    )
    tenv = read_target_env(str(tmp_path))
    assert "DATABASE_URL" in tenv.env
    assert tenv.services == ("postgres", "redis")
    assert tenv.setup == (("ci-step-1", "pnpm --filter @jo-ken-po/db db:migrate"),)


def test_read_target_env_sem_github_e_vazio(tmp_path: Path) -> None:
    # repo sem .github/workflows e sem package.json → TargetEnv vazio (no-op, degrada normal).
    tenv = read_target_env(str(tmp_path))
    assert tenv.env == {} and tenv.services == () and tenv.setup == ()


_WF_STEPS = """
jobs:
  verify:
    steps:
      - uses: actions/checkout@v7
      - name: Liberar espaço
        run: docker system prune -f
      - name: Install
        run: pnpm install --frozen-lockfile
      - name: Prisma generate
        run: pnpm --filter @jo-ken-po/db db:generate
      - name: DB migrate
        run: pnpm --filter @jo-ken-po/db db:migrate
      - name: Criar role de app
        run: |
          docker run -i --rm --network host -e PGPASSWORD=jokenpo postgres:16 \\
            psql -h 127.0.0.1 -U jokenpo -d jokenpo_test -f - < scripts/db-app-role.sql
      - name: Typecheck
        run: pnpm typecheck
      - name: Test
        run: pnpm test
"""


def test_parse_ci_setup_steps_pega_so_setup() -> None:
    from roboto.app.target_env import parse_ci_setup_steps

    steps = parse_ci_setup_steps(_WF_STEPS)
    # mantém db:generate, db:migrate e o criar-role (psql); pula checkout(uses)/prune/install/gate
    assert any("db:generate" in s for s in steps)
    assert any("db:migrate" in s for s in steps)
    assert any("db-app-role.sql" in s for s in steps)  # O ASSET A MAIS (role) foi capturado
    assert not any("pnpm install" in s for s in steps)  # deps = ruído
    assert not any("prune" in s for s in steps)  # limpeza = ruído
    assert not any(s.strip() in ("pnpm test", "pnpm typecheck") for s in steps)  # gate = separado


def test_parse_ci_setup_steps_ordem_preservada() -> None:
    from roboto.app.target_env import parse_ci_setup_steps

    steps = parse_ci_setup_steps(_WF_STEPS)
    assert steps.index(next(s for s in steps if "db:generate" in s)) < steps.index(
        next(s for s in steps if "db:migrate" in s)
    )  # generate antes de migrate (ordem do workflow)


def test_parse_compose_services() -> None:
    from roboto.app.target_env import parse_compose_services

    yml = """
services:
  db:
    image: postgres:16
    environment: {POSTGRES_USER: app, SECRET: "${PASS}"}
  cache:
    image: redis:7
    environment: ["REDIS_PASS=x"]
  nada: {build: .}
"""
    svcs = {s.name: s for s in parse_compose_services(yml)}
    assert svcs["db"].image == "postgres:16"
    assert svcs["db"].env == {"POSTGRES_USER": "app"}  # ${} fora
    assert svcs["cache"].env == {"REDIS_PASS": "x"}  # formato lista
    assert "nada" not in svcs  # sem image → ignorado


def test_parse_ci_setup_steps_para_no_primeiro_gate() -> None:
    from roboto.app.target_env import parse_ci_setup_steps

    wf = """
jobs:
  v:
    steps:
      - run: pnpm db:migrate
      - run: docker run psql < role.sql
      - run: node scripts/check-design.mjs --all
      - run: pnpm check:i18n
      - run: pnpm --filter x test:int
"""
    steps = parse_ci_setup_steps(wf)
    assert any("db:migrate" in s for s in steps)
    assert any("role.sql" in s for s in steps)  # setup antes do 1º check
    assert not any("check-design" in s for s in steps)  # check → parou aqui
    assert not any("check:i18n" in s for s in steps)
    assert not any("test:int" in s for s in steps)  # test:int não vira setup
