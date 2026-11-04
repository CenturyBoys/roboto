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


def _install_failing_hook(path: Path) -> None:
    hooks = path / ".githooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text('#!/bin/sh\necho "lint falhou: formate o arquivo"\nexit 1\n')
    hook.chmod(0o755)
    subprocess.run(["git", "-C", str(path), "config", "core.hooksPath", ".githooks"], check=True)


async def test_commit_all_raises_when_pre_commit_hook_blocks(tmp_path: Path) -> None:
    # falha silenciosa #3: hook que barra o commit NÃO pode virar "diff vazio" — levanta o motivo.
    _init_repo(tmp_path)
    _install_failing_hook(tmp_path)
    (tmp_path / "novo.txt").write_text("conteudo")
    git = SubprocessGit(str(tmp_path))
    with pytest.raises(GitError) as exc:
        await git.commit_all("feat: algo")
    assert "lint falhou" in str(exc.value)  # o motivo do hook aparece


async def test_commit_all_tolerates_nothing_to_commit(tmp_path: Path) -> None:
    # árvore limpa (nada staged) → NÃO levanta (o ciclo decide o "diff vazio")
    _init_repo(tmp_path)
    git = SubprocessGit(str(tmp_path))
    await git.commit_all("chore: nada mudou")  # não deve levantar


async def test_prepare_branch_ok_local(tmp_path: Path) -> None:
    # caminho feliz: checkout -B numa branch local funciona e NÃO levanta
    _init_repo(tmp_path)
    git = SubprocessGit(str(tmp_path))
    await git.prepare_branch("feature/x")  # não deve levantar
    branch = (await git._git_out("rev-parse", "--abbrev-ref", "HEAD")).strip()
    assert branch == "feature/x"


def _init_origin_clone(tmp_path: Path) -> Path:
    """Cria um 'origin' com a base 'develop' e clona em /work — cenário do runner."""
    origin = tmp_path / "origin"
    _init_repo(origin)
    subprocess.run(["git", "-C", str(origin), "branch", "-M", "develop"], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "t"], check=True)
    return work


def _simulate_dirty_run(work: Path) -> None:
    """Run anterior deixou no /work: 1 commit (tracked) + 1 arquivo untracked."""
    (work / "adr.md").write_text("ADR do run A")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "run A"], check=True)
    (work / "lixo.txt").write_text("stray do run A")  # untracked


async def test_reset_to_base_limpa_contaminacao_do_run_anterior(tmp_path: Path) -> None:
    # #225: run A deixou commit + untracked no /work; reset_to_base volta à base LIMPA p/ o run B
    work = _init_origin_clone(tmp_path)
    _simulate_dirty_run(work)

    git = SubprocessGit(str(work))
    await git.reset_to_base("develop")

    assert not (work / "adr.md").exists()  # tracked do run A: some no reset --hard
    assert not (work / "lixo.txt").exists()  # untracked: some no clean -fd
    assert (work / "a.txt").exists()  # base intacta
