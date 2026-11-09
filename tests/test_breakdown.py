"""Breakdown de épico (refino): detecção determinística + parse de sub-issues esqueleto."""

from __future__ import annotations

from roboto.agents.breakdown import (
    Breakdown,
    SubIssueSkeleton,
    is_architectural,
    is_epic,
    needs_ux,
    parse_breakdown,
    review_breakdown,
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
    body = skeleton_body(item, dep_number=42)
    assert "mascarar email" in body
    # a frase "Depende de #42" tem que ser detectada pelo gate blocked_by (app/deps.py)
    assert blocked_by(body) == [42]


def test_skeleton_body_primeiro_item_sem_dependencia() -> None:
    item = SubIssueSkeleton(title="ADR", points=[], depends_on_prev=False)
    body = skeleton_body(item, dep_number=None)
    assert blocked_by(body) == []
    assert "(a detalhar)" in body  # sem pontos → placeholder


def test_skeleton_body_semeia_pesquisa_em_decisao() -> None:
    # sub-issue de DECISÃO (convenção) → semeia o bloco 🔎 + queries-semente dos pontos de pesquisa
    item = SubIssueSkeleton(
        title="Definir convenção de versão",
        points=["Pesquisar melhores práticas de versionamento", "Escolher entre prefixo e header"],
        depends_on_prev=False,
    )
    body = skeleton_body(item, dep_number=None)
    assert "🔎 Pesquisa" in body
    assert "1. melhores práticas de versionamento" in body  # tirou o verbo "Pesquisar"
    assert "2. prefixo e header" in body  # tirou "Escolher entre"


def test_skeleton_body_sem_pesquisa_em_tarefa_comum() -> None:
    # pesquisa NÃO é obrigatória: tarefa de implementação não ganha o bloco 🔎
    item = SubIssueSkeleton(
        title="Implementar endpoint de versão",
        points=["Criar rota /version", "Retornar JSON"],
        depends_on_prev=True,
    )
    body = skeleton_body(item, dep_number=10)
    assert "🔎" not in body


# --- dependência NOMEADA (DAG) no parser ---


def test_parse_dependencia_nomeada_forma_dag() -> None:
    text = (
        "ITEM: pesquisa\n- levantar\n"
        "ITEM: adr\n- decidir\nDEPENDE: #1\n"
        "ITEM: schema\n- campos\nDEPENDE: #2\n"
        "ITEM: scheduler\n- worker\nDEPENDE: #3\n"
        "ITEM: quorum\n- regra\nDEPENDE: #3\n"  # pendura no schema, NÃO no scheduler
    )
    bd = parse_breakdown(text)
    assert [it.depends_on_index for it in bd.items] == [None, 0, 1, 2, 2]
    # quórum (idx 4) depende do schema (idx 2), não do item imediatamente anterior
    assert bd.items[4].depends_on_index == 2
    assert bd.items[4].depends_on_prev is False


def test_parse_dependencia_nomeada_invalida_cai_no_default() -> None:
    # "#9" não aponta p/ item anterior válido → ignora e encadeia no anterior (default conservador)
    bd = parse_breakdown("ITEM: a\n- x\nITEM: b\n- y\nDEPENDE: #9\n")
    assert bd.items[1].depends_on_index is None
    assert bd.items[1].depends_on_prev is True


# --- detectores de dimensão ---


def test_is_architectural_detecta_decisao() -> None:
    assert is_architectural("Épico: scheduler durável", "worker idempotente, exactly-once") is True
    assert is_architectural("Precisa de ADR", "duas visões → decisão") is True
    assert is_architectural("Ajustar copy do botão", "trocar texto") is False


def test_needs_ux_detecta_usuario_final() -> None:
    assert needs_ux("Fluxo do jogador", "recebe notificação na tela e vê ranking") is True
    assert needs_ux("Migração de índice no banco", "adicionar coluna") is False


# --- gate determinístico de cobertura (review_breakdown) ---


def _bd(*titles: str) -> Breakdown:
    return Breakdown(items=[SubIssueSkeleton(t, [], i > 0) for i, t in enumerate(titles)])


def test_review_avisa_arquitetural_sem_pesquisa_e_adr() -> None:
    body = "scheduler durável com jobs idempotentes e exactly-once"
    bd = _bd("Implementar scheduler", "Implementar regras")
    warns = review_breakdown("Épico: torneios", body, bd)
    assert any("PESQUISA" in w for w in warns)
    assert any("ADR" in w for w in warns)


def test_review_ok_quando_arquitetural_tem_pesquisa_e_adr() -> None:
    body = "scheduler durável idempotente"
    bd = _bd("Pesquisa de boas práticas", "Arquitetura — duas visões → ADR", "Implementar worker")
    warns = review_breakdown("Épico: torneios", body, bd)
    assert not any("PESQUISA" in w or "ADR" in w for w in warns)


def test_review_avisa_usuario_final_sem_ui() -> None:
    body = "jogador recebe notificação e vê o ranking na tela"
    bd = _bd("Implementar scheduler", "Implementar quórum")
    warns = review_breakdown("Épico: torneio", body, bd)
    assert any("UI/JORNADA" in w for w in warns)


def test_review_avisa_doc_no_ultimo_item() -> None:
    bd = _bd("Implementar", "Documentar fluxo e regras")
    warns = review_breakdown("Épico X", "coisa simples", bd)
    assert any("ÚLTIMO" in w for w in warns)


def test_review_avisa_item_inchado() -> None:
    bd = _bd("Implementar prazos, extensão, finalização, ranking e prêmio")
    warns = review_breakdown("Épico X", "simples", bd)
    assert any("INCHADA" in w for w in warns)


# --- seeding por dimensão no corpo do esqueleto ---


def test_skeleton_body_semeia_ux_em_item_de_jornada() -> None:
    item = SubIssueSkeleton("UI da jornada do torneio", ["telas de inscrição e resultado"], False)
    body = skeleton_body(item, dep_number=None)
    assert "🎭 Jornada & UI" in body


def test_skeleton_body_semeia_migracao_em_item_de_schema() -> None:
    item = SubIssueSkeleton("Modelo de dados do torneio", ["adicionar campo scheduledAt"], False)
    body = skeleton_body(item, dep_number=None)
    assert "🗄️ Migração" in body
    assert "Backfill" in body


def test_skeleton_body_semeia_garantias_em_item_duravel() -> None:
    item = SubIssueSkeleton("Implementar scheduler/worker durável", ["job idempotente"], False)
    body = skeleton_body(item, dep_number=None)
    assert "🔒 Garantias transversais" in body
