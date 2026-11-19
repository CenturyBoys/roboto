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
