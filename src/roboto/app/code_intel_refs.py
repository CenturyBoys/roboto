"""Pré-fetch de símbolos da issue → direciona o code-intel (trilha F, #223).

Medido: o motor subusa o code-intel (cai em Bash/Read) — e quando usa, nem sempre nos símbolos
certos (causa do import órfão do #310). Em vez de só pedir "use code-intel", o harness **extrai
determinísticamente** os símbolos prováveis da issue (spans em crase + identificadores CamelCase/
snake) e injeta uma DIRETIVA pra o motor rodar `find_references` NELES antes de editar.
Puro e testável; a execução do `find_references` pelo próprio harness (como o `repo_map` do
`code_intel_brief`) é a camada que valida no PoC vivo.
"""

from __future__ import annotations

import re

# identificador de código: CamelCase, snake_case, dotted (ex.: app.foo), ≥3 chars, começa com letra.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{2,}")
_BACKTICK = re.compile(r"`([^`\n]{2,60})`")
# palavras comuns de prosa que NÃO são símbolo (reduz ruído).
_STOP = frozenset(
    {
        "the", "and", "for", "with", "que", "com", "para", "não", "uma", "dos", "das", "issue",
        "critérios", "aceite", "contexto", "escopo", "pull", "request", "github", "https", "http",
        "test", "tests", "feat", "fix", "docs", "chore", "todo", "done",
    }
)


def extract_symbols(text: str, *, limit: int = 8) -> list[str]:
    """Símbolos prováveis da issue (crase primeiro, depois identificadores), dedup. Puro."""
    seen: dict[str, None] = {}
    for raw in _BACKTICK.findall(text):
        for tok in _IDENT.findall(raw):
            if _is_symbol(tok):
                seen.setdefault(tok, None)
    for tok in _IDENT.findall(text):  # fora de crase: só CamelCase/snake/dotted (mais seletivo)
        if _is_symbol(tok) and (any(c.isupper() for c in tok[1:]) or "_" in tok or "." in tok):
            seen.setdefault(tok, None)
    return list(seen)[:limit]


def _is_symbol(tok: str) -> bool:
    return tok.lower() not in _STOP and not tok.isdigit()


def symbols_directive(symbols: list[str]) -> str:
    """Bloco pro prompt: manda rodar code-intel NOS símbolos antes de editar. Vazio se não há."""
    if not symbols:
        return ""
    nomes = ", ".join(f"`{s}`" for s in symbols)
    return (
        "SÍMBOLOS PROVÁVEIS desta issue: " + nomes + ".\n"
        "ANTES de editar, rode o code-intel NELES: `find_symbol` p/ localizar e `find_references`/"
        "`call_hierarchy` p/ ver quem usa e o que quebra. Isso evita import órfão / quebrar quem "
        "depende (mais barato que Read/Bash e correto por LSP, trilha F)."
    )
