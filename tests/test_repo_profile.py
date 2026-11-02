"""Perfil do repo (determinístico): extrai pm/monorepo/scripts e orienta rodar via o pm do repo."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.repo_profile import build_repo_profile, read_agents_conventions


def test_profile_pnpm_monorepo(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"packageManager": "pnpm@10.34.7", "scripts": {"test": "vitest", "lint": "eslint ."}}
        )
    )
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - packages/*\n")
    (tmp_path / "AGENTS.md").write_text("# regras\n")
    status = tmp_path / "env-status"
    status.write_text("✅ PRONTO: pnpm 10.34.7 + deps instaladas")

    profile = build_repo_profile(str(tmp_path), env_status_path=status)

    assert "pnpm@10.34.7" in profile and "MONOREPO" in profile
    assert "NÃO rode install" in profile  # deps já instaladas
    assert "test=`vitest`" in profile
    assert "--filter" in profile  # orienta rodar por pacote no monorepo
    assert "NUNCA crie scripts de teste" in profile  # sem gambiarra .cjs
    assert "AGENTS.md" in profile


def test_profile_vazio_sem_package_json(tmp_path: Path) -> None:
    # não é projeto JS → nada a dizer (não polui o prompt)
    assert build_repo_profile(str(tmp_path)) == ""


def test_conventions_inject_agents_md_content(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Regras\n- Use Result, não exceção.\n")
    block = read_agents_conventions(str(tmp_path))
    assert "CONVENÇÕES DO REPO-ALVO (AGENTS.md" in block
    assert "Use Result, não exceção." in block  # conteúdo REAL injetado, não só "leia o arquivo"


def test_conventions_fallback_to_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("convenção X")
    block = read_agents_conventions(str(tmp_path))
    assert "CLAUDE.md" in block and "convenção X" in block


def test_conventions_prefers_agents_over_claude(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("regra do agents")
    (tmp_path / "CLAUDE.md").write_text("regra do claude")
    block = read_agents_conventions(str(tmp_path))
    assert "regra do agents" in block and "regra do claude" not in block


def test_conventions_truncates_respecting_token_budget(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("x" * 20_000)
    block = read_agents_conventions(str(tmp_path), max_chars=500)
    assert "truncado em 500 de 20000 chars" in block
    assert len(block) < 1000  # capado de verdade


def test_conventions_empty_when_absent(tmp_path: Path) -> None:
    assert read_agents_conventions(str(tmp_path)) == ""
