"""Scheduling ciente de dependência (Trilha J): parse de "blocked by #N"."""

from __future__ import annotations

from roboto.app.deps import blocked_by


def test_detects_blocking_phrases() -> None:
    assert blocked_by("proteger XP (bloqueada por #79)") == [79]
    assert blocked_by("This is blocked by #79") == [79]
    assert blocked_by("depends on #80") == [80]
    assert blocked_by("depende de #81") == [81]


def test_multiple_blockers_deduped() -> None:
    assert blocked_by("blocked by #79, #80 and #79") == [79, 80]


def test_ignores_mere_relation() -> None:
    # "relaciona-se a / relates to / refs" NÃO é bloqueio
    assert blocked_by("Relaciona-se a: #79 — gamificação") == []
    assert blocked_by("relates to #79 · refs #80") == []
    assert blocked_by("Closes #10\nRefs #11") == []


def test_no_blocker() -> None:
    assert blocked_by("## Contexto\nnada aqui") == []
    assert blocked_by("") == []
