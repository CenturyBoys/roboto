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
    assert tenv.setup == (("db:migrate", "pnpm -s db:migrate"),)


def test_read_target_env_sem_github_e_vazio(tmp_path: Path) -> None:
    # repo sem .github/workflows e sem package.json → TargetEnv vazio (no-op, degrada normal).
    tenv = read_target_env(str(tmp_path))
    assert tenv.env == {} and tenv.services == () and tenv.setup == ()
