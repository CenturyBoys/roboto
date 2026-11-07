"""Âncora de papel (persona) atrás de flag: resolução da flag e prefixo do prompt."""

from __future__ import annotations

from roboto.persona import (
    IMPL_PERSONA_DEFAULT,
    REFINE_PERSONA_DEFAULT,
    anchor_line,
    resolve_persona,
)


def test_flag_desligada_explicita_vira_baseline() -> None:
    for off in ("0", "off", "false", "no", "OFF"):
        assert resolve_persona(off, REFINE_PERSONA_DEFAULT) == ""


def test_default_ligado_quando_ausente_ou_on() -> None:
    # ausente/vazio = LIGADA (novo default), além de "1"/"on"/"true"
    for on in ("", "  ", "1", "on", "TRUE"):
        assert resolve_persona(on, REFINE_PERSONA_DEFAULT) == REFINE_PERSONA_DEFAULT
    assert resolve_persona("on", IMPL_PERSONA_DEFAULT) == IMPL_PERSONA_DEFAULT


def test_texto_custom_vira_ancora() -> None:
    assert resolve_persona("Você é um QA", "ignorado") == "Você é um QA"


def test_anchor_line_prefixa_ou_vazio() -> None:
    assert anchor_line("") == ""
    assert anchor_line("Você é X") == "Você é X\n\n"
