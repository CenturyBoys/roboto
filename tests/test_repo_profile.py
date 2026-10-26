"""Perfil do repo (determinístico): extrai pm/monorepo/scripts e orienta rodar via o pm do repo."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.repo_profile import build_repo_profile


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
