"""Assist determinístico de `noUncheckedIndexedAccess`: quando o typecheck reprova com TS2322
'X | undefined' não atribuível a 'X', o harness injeta a dica concreta do swap seguro. Fecha o gap
do A/B T1 (qwen E glm travaram no MESMO ponto do Fisher-Yates)."""

from __future__ import annotations

from roboto.app.pr_cycle import ts_index_safety_hint

# erro real do qwen no A/B (swap por destructuring)
_QWEN = (
    "src/tournament/bracket.ts(175,6): error TS2322: "
    "Type 'Player | undefined' is not assignable to type 'Player'."
)
# erro real do GLM (swap genérico com `!` só de um lado)
_GLM = (
    "src/tournament/bracket.ts(65,5): error TS2322: "
    "Type 'T | undefined' is not assignable to type 'T'."
)


def test_casa_o_erro_do_qwen() -> None:
    hint = ts_index_safety_hint(_QWEN)
    assert hint and "noUncheckedIndexedAccess" in hint
    assert "swap seguro" in hint


def test_casa_o_erro_do_glm() -> None:
    assert ts_index_safety_hint(_GLM) != ""


def test_ignora_erro_nao_relacionado() -> None:
    # outro TS2322 (não é o padrão `X | undefined` -> `X`) não dispara a dica
    other = "error TS2322: Type 'string' is not assignable to type 'number'."
    assert ts_index_safety_hint(other) == ""
    assert ts_index_safety_hint("") == ""


def test_so_dispara_no_mesmo_tipo_dos_dois_lados() -> None:
    # 'A | undefined' -> 'B' (tipos diferentes) NÃO é o caso de índice; não dispara
    mism = "error TS2322: Type 'Foo | undefined' is not assignable to type 'Bar'."
    assert ts_index_safety_hint(mism) == ""
