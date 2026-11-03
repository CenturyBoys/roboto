"""Breakdown de épico (refino): detecção determinística + parse de sub-issues esqueleto."""

from __future__ import annotations

from roboto.agents.breakdown import (
    SubIssueSkeleton,
    is_epic,
    parse_breakdown,
    skeleton_body,
)
from roboto.app.deps import blocked_by

# --- detecção de épico ---


def test_epic_word_in_title_is_epic() -> None:
    assert is_epic("Épico: Rate limiting transversal", "") is True
    assert is_epic("[EPIC] gamificação", "") is True


def test_normal_issue_is_not_epic() -> None:
    assert is_epic("feat: adicionar botão de logout", "## Contexto\numa coisa só") is False


def test_epic_by_body_signals() -> None:
    # palavra "épico" no corpo + muitos checkboxes = ≥2 sinais
    body = "Este épico cobre várias frentes.\n" + "\n".join(f"- [ ] item {i}" for i in range(9))
    assert is_epic("feat: proteção transversal", body) is True


def test_one_signal_not_enough() -> None:
    # só muitos checkboxes, sem outros sinais → não é épico (evita falso-positivo)
    body = "\n".join(f"- [ ] item {i}" for i in range(9))
    assert is_epic("feat: checklist grande", body) is False


def test_epicentro_nao_dispara() -> None:
    # "épico" é palavra; "epicentro" não deve casar
    assert is_epic("fix: corrigir epicentro do bug", "nada aqui") is False


# --- parse do breakdown ---


def test_parse_items_and_points() -> None:
    text = (
        "ITEM: ADR + regra no AGENTS.md\n"
        "- escrever ADR\n"
        "- citar no AGENTS.md\n"
        "ITEM: logger com redaction\n"
        "- mascarar email/telefone\n"
    )
    bd = parse_breakdown(text)
    assert [i.title for i in bd.items] == ["ADR + regra no AGENTS.md", "logger com redaction"]
    assert bd.items[0].points == ["escrever ADR", "citar no AGENTS.md"]
    # encadeamento: 1º independente, 2º depende do anterior
    assert bd.items[0].depends_on_prev is False
    assert bd.items[1].depends_on_prev is True


def test_depende_nenhuma_quebra_a_cadeia() -> None:
    text = "ITEM: A\n- x\nITEM: B\nDEPENDE: nenhuma\n- y\n"
    bd = parse_breakdown(text)
    assert bd.items[1].depends_on_prev is False  # marcado independente


def test_parse_ignora_ruido_antes_do_primeiro_item() -> None:
    bd = parse_breakdown("blá blá conversa\n- ponto solto\nITEM: real\n- p1\n")
    assert len(bd.items) == 1
    assert bd.items[0].title == "real"


def test_parse_vazio() -> None:
    assert parse_breakdown("").items == []


# --- corpo do esqueleto casa com o gate de dependência ---


def test_skeleton_body_encadeia_no_gate() -> None:
    item = SubIssueSkeleton(title="logger", points=["mascarar email"], depends_on_prev=True)
    body = skeleton_body(item, prev_number=42)
    assert "mascarar email" in body
    # a frase "Depende de #42" tem que ser detectada pelo gate blocked_by (app/deps.py)
    assert blocked_by(body) == [42]


def test_skeleton_body_primeiro_item_sem_dependencia() -> None:
    item = SubIssueSkeleton(title="ADR", points=[], depends_on_prev=False)
    body = skeleton_body(item, prev_number=None)
    assert blocked_by(body) == []
    assert "(a detalhar)" in body  # sem pontos → placeholder
