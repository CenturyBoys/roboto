"""SubprocessGit: falhas de git NÃO podem ser engolidas (push/checkout levantam GitError)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from roboto.app.git_ops import GitError, SubprocessGit

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git ausente")


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    (path / "a.txt").write_text("x")
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


async def test_push_raises_when_remote_missing(tmp_path: Path) -> None:
    # sem remote 'origin' configurado → push falha; antes isso era engolido e virava 422 no open_pr
    _init_repo(tmp_path)
    git = SubprocessGit(str(tmp_path))
    with pytest.raises(GitError) as exc:
        await git.push("roboto/run-1")
    assert "push" in str(exc.value)  # mensagem aponta o comando que falhou


async def test_checkout_remote_raises_when_branch_absent(tmp_path: Path) -> None:
    # fetch de uma branch remota inexistente (sem origin) → levanta, não segue no estado errado
    _init_repo(tmp_path)
    git = SubprocessGit(str(tmp_path))
    with pytest.raises(GitError):
        await git.checkout_remote("roboto/nao-existe")


async def test_prepare_branch_ok_local(tmp_path: Path) -> None:
    # caminho feliz: checkout -B numa branch local funciona e NÃO levanta
    _init_repo(tmp_path)
    git = SubprocessGit(str(tmp_path))
    await git.prepare_branch("feature/x")  # não deve levantar
    branch = (await git._git_out("rev-parse", "--abbrev-ref", "HEAD")).strip()
    assert branch == "feature/x"
