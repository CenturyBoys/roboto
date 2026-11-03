"""Brief do code-intel (trilha F): formatação do catálogo + mapa pro prompt."""

from __future__ import annotations

from roboto.app.code_intel_brief import format_brief

_TOOLS = [
    ("quick_fix", "aplica quick fixes"),
    ("find_symbol", "acha a definição de um símbolo"),
    ("rename_symbol", "renomeia um símbolo e todas as refs via LSP"),
    ("repo_map", "mapa do repositório"),
]


def test_format_brief_lista_tools_e_prioriza() -> None:
    out = format_brief(_TOOLS)
    assert "FERRAMENTAS code-intel" in out
    # tools prioritárias vêm antes da não-prioritária (quick_fix)
    assert out.index("find_symbol") < out.index("quick_fix")
    assert out.index("repo_map") < out.index("quick_fix")
    # cada tool aparece com o nome
    for name, _ in _TOOLS:
        assert name in out


def test_format_brief_vazio_sem_tools() -> None:
    assert format_brief([]) == ""


def test_format_brief_inclui_mapa_truncado() -> None:
    mapa = "x" * 5000
    out = format_brief(_TOOLS, repo_map=mapa)
    assert "MAPA INICIAL DO REPO" in out
    assert "truncado" in out  # cap aplicado
    assert len(out) < 5000  # não despejou o mapa inteiro


def test_format_brief_sem_mapa_nao_poe_secao() -> None:
    out = format_brief(_TOOLS, repo_map="   ")
    assert "MAPA INICIAL DO REPO" not in out
