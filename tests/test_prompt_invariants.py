"""Canário de invariantes de prompt (inspirado no `check-rule-copies.js` do Ponytail).

Nossa arquitetura não replica o prompt por motor (um build, vários motores), mas os prompts de PAPEL
(persona por papel, [[persona-por-papel]]) e de REVIEW carregam frases **load-bearing** que DEFINEM
o comportamento. Mudar a redação é ok; PERDER o conceito não — se um invariante sumir numa edição
silenciosa, a política derivou sem ninguém notar. Este teste quebra o CI nesse caso."""

from __future__ import annotations

from roboto.agents.review import REVIEW_PR_STRUCT_SYSTEM
from roboto.persona import IMPL_PERSONA_DEFAULT, REFINE_PERSONA_DEFAULT

# (nome do prompt, frases que TÊM que sobreviver — cada uma é uma âncora de comportamento).
_INVARIANTS: dict[str, tuple[str, list[str]]] = {
    "impl_persona": (
        IMPL_PERSONA_DEFAULT,
        ["ENGENHEIRO DE SOFTWARE SÊNIOR", "CONVENÇÕES", "teste", "escopo mínimo", "regress"],
    ),
    "refine_persona": (
        REFINE_PERSONA_DEFAULT,
        ["TECH LEAD", "FUNDAMENTA", "CRITÉRIOS", "NÃO implementa"],
    ),
    "review_struct": (
        REVIEW_PR_STRUCT_SYSTEM,
        ["SEM CASO, SEM FINDING", "CASO CONCRETO", "shortcut", "ORDEM DE IMPORTÂNCIA", "menor"],
    ),
}


def test_invariantes_de_papel_e_review_sobrevivem() -> None:
    faltando = {
        nome: [f for f in frases if f not in prompt]
        for nome, (prompt, frases) in _INVARIANTS.items()
        if any(f not in prompt for f in frases)
    }
    assert not faltando, f"invariante de prompt sumiu (a política derivou sem querer): {faltando}"
