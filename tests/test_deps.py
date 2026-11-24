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


def test_tolera_markdown_entre_frase_e_ref() -> None:
    # REGRESSÃO (run-1047): markdown entre a frase e o #N NÃO pode dropar a dependência em silêncio.
    assert blocked_by("> **Depende de:** #281") == [281]
    assert blocked_by("**Depende de:** #397, #398") == [397, 398]
    assert blocked_by("depende de `#5`") == [5]
    assert blocked_by("Bloqueada por: **#79**") == [79]


def test_nao_inventa_dep_de_prosa() -> None:
    # frase de bloqueio longe do #N (prosa) NÃO vira dependência — limite curto entre frase e ref.
    assert blocked_by("depende de fazer isso antes de mexer no #9") == []
    # "independe de" (oposto) não pode casar o "depende de" interno
    assert blocked_by("Este trabalho independe de #9") == []
