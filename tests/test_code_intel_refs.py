"""Testes da extração de símbolos p/ direcionar o code-intel (#223)."""

from __future__ import annotations

from roboto.app.code_intel_refs import extract_symbols, symbols_directive


def test_extrai_simbolos_de_crase_e_camelcase() -> None:
    text = "Implementar a função `casRoomState`. O `setBackendForTest` injeta FakeRedis no módulo."
    syms = extract_symbols(text)
    assert "casRoomState" in syms  # span em crase
    assert "setBackendForTest" in syms  # CamelCase (em crase)
    assert "FakeRedis" in syms  # CamelCase fora de crase


def test_ignora_prosa_e_numeros() -> None:
    assert extract_symbols("para o contexto com que issue não 123") == []


def test_dedup_e_limite() -> None:
    text = "`Foo` `Foo` `Bar` `Baz` `Qux` `A_b` `C_d` `E_f` `G_h` `I_j`"
    syms = extract_symbols(text, limit=3)
    assert len(syms) == 3
    assert syms[0] == "Foo"  # ordem preservada, sem repetir


def test_directive() -> None:
    assert symbols_directive([]) == ""
    d = symbols_directive(["Foo", "bar_baz"])
    assert "Foo" in d and "bar_baz" in d and "find_references" in d
