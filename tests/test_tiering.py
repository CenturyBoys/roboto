"""Classificador de tier: grande/arquitetural -> forte; resto -> barato (determinístico)."""

from __future__ import annotations

from roboto.app.tiering import classificar_tier


def test_tarefa_pequena_fica_no_barato() -> None:
    d = classificar_tier(
        "feat(web): adicionar link Mapa no rodapé",
        "Adicione um <Link href=/mapa> em site-footer.tsx usando a chave menu.map.",
    )
    assert d.forte is False


def test_muitos_arquivos_vira_forte() -> None:
    # limiar subido p/ 6 (#242): tarefa com MUITOS arquivos citados vai pro forte
    arqs = ", ".join(f"apps/web/src/{c}.tsx" for c in "abcdef")  # 6 arquivos
    d = classificar_tier("feat: refatorar capacidades", f"toca {arqs}")
    assert d.forte is True
    assert "arquivos" in d.motivo


def test_poucos_arquivos_fica_no_barato() -> None:
    # 3 arquivos (antes virava forte) agora fica no barato — o degrau cobre o resgate
    d = classificar_tier(
        "feat: ajuste", "toca apps/web/src/a.tsx, apps/web/src/b.tsx e apps/web/src/c.tsx"
    )
    assert d.forte is False


def test_arquitetural_com_corpo_extenso_vira_forte() -> None:
    corpo = (
        "O ADR 0042 pede uma camada ports/adapters para abstrair capacidades de plataforma. "
        "Precisamos refatorar a detecção e o ciclo de permissão sem duplicação. " * 3
    )
    d = classificar_tier("feat(platform): camada de capacidades", corpo)
    assert d.forte is True


def test_keyword_arquitetural_em_corpo_curto_nao_basta() -> None:
    d = classificar_tier("chore: nota", "pequeno refactor de nome")
    assert d.forte is False
