"""Testes da higiene de commit (#279, app.commit_hygiene)."""

from __future__ import annotations

from roboto.app.commit_hygiene import strip_ai_trailers


def test_remove_co_author_claude() -> None:
    msg = "feat(x): y\n\nCorpo.\n\nRefs #1\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
    out = strip_ai_trailers(msg)
    assert "Claude" not in out
    assert "noreply@anthropic" not in out
    assert "Refs #1" in out
    assert out.rstrip().endswith("Refs #1")  # sem linhas em branco sobrando


def test_remove_rodape_de_ferramenta() -> None:
    msg = "fix: z\n\n🤖 Generated with [Claude Code]\n"
    assert "Generated" not in strip_ai_trailers(msg)


def test_preserva_co_autor_humano() -> None:
    msg = "feat: a\n\nCo-authored-by: Ximit <im.ximit@gmail.com>\n"
    out = strip_ai_trailers(msg)
    assert "Ximit" in out


def test_noop_quando_limpa() -> None:
    msg = "feat: a\n\nRefs #2\n"
    assert strip_ai_trailers(msg) == msg


def test_install_repo_hook_respeita_core_hookspath_local(tmp_path, monkeypatch) -> None:
    # simula o alvo: core.hooksPath=.githooks LOCAL (como o prepare do jo-ken-po) → o stripper
    # tem que ser instalado EM .githooks/commit-msg, não em .git/hooks (senão é bypassado, #323).
    import subprocess
    from pathlib import Path

    from roboto.app.commit_hygiene import install_repo_hook

    repo = tmp_path / "alvo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".githooks").mkdir()
    (repo / ".githooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n")
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"], check=True)

    path = install_repo_hook(str(repo))
    assert Path(path) == repo / ".githooks" / "commit-msg"  # no path EFETIVO, não .git/hooks
    assert "co-authored-by" in Path(path).read_text().lower()
    assert (repo / ".githooks" / "pre-commit").exists()  # preserva o pre-commit do repo


def test_install_repo_hook_encadeia_commit_msg_existente(tmp_path) -> None:
    import subprocess

    from roboto.app.commit_hygiene import install_repo_hook

    repo = tmp_path / "r2"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "commit-msg").write_text("#!/bin/sh\necho repo-hook\n")

    install_repo_hook(str(repo))
    assert (hooks / "commit-msg.repo").exists()  # o commit-msg do repo foi preservado
    novo = (hooks / "commit-msg").read_text()
    assert "commit-msg.repo" in novo and "$1.hyg" in novo  # encadeia repo → stripper


def test_hook_instalado_limpa_de_verdade(tmp_path) -> None:
    import subprocess

    from roboto.app.commit_hygiene import install_repo_hook

    repo = tmp_path / "r3"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    hook = install_repo_hook(str(repo))
    msg = repo / "MSG"
    msg.write_text("feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
    subprocess.run([hook, str(msg)], check=True)  # roda o hook self-contained (sem import)
    out = msg.read_text()
    assert "Claude" not in out and "feat: x" in out  # trailer removido, resto intacto
