"""Validação de pré-condições do runtime (Trilha K)."""

from __future__ import annotations

from pathlib import Path

from roboto.app.preflight import check


def test_all_ok(tmp_path: Path) -> None:
    r = check(
        env={"OPENROUTER_API_KEY": "sk-x"},
        required_keys=("OPENROUTER_API_KEY",),
        workdir=str(tmp_path),
        min_disk_mb=100,
        disk_free_mb=5000,
    )
    assert r.ok and r.failures == []


def test_missing_env_fails(tmp_path: Path) -> None:
    r = check(
        env={}, required_keys=("OPENROUTER_API_KEY",), workdir=str(tmp_path)
    )
    assert not r.ok
    assert any(c.name == "env:OPENROUTER_API_KEY" and not c.ok for c in r.failures)


def test_missing_workdir_fails() -> None:
    r = check(env={}, required_keys=(), workdir="/caminho/que/nao/existe")
    assert not r.ok
    assert any(c.name == "workdir" and not c.ok for c in r.failures)


def test_low_disk_fails(tmp_path: Path) -> None:
    r = check(
        env={}, required_keys=(), workdir=str(tmp_path), min_disk_mb=500, disk_free_mb=100
    )
    assert not r.ok
    assert any(c.name == "disco" for c in r.failures)


def test_disk_skipped_when_not_measured(tmp_path: Path) -> None:
    r = check(env={}, required_keys=(), workdir=str(tmp_path), min_disk_mb=500, disk_free_mb=None)
    assert r.ok  # sem medição de disco → não checa
    assert not any(c.name == "disco" for c in r.checks)
