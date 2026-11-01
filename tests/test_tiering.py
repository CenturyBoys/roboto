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
    d = classificar_tier(
        "feat: refatorar capacidades",
        "toca apps/web/src/a.tsx, apps/web/src/b.tsx e apps/web/src/c.tsx",
    )
    assert d.forte is True
    assert "arquivos" in d.motivo


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
