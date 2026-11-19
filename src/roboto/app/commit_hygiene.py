"""Higiene da mensagem de commit (#279): remove atribuição de co-autor de IA / rodapé de ferramenta.

A org **proíbe** `Co-Authored-By: Claude` e rodapés "Generated with …" em commit/PR — *mesmo que o
harness sugira* (AGENTS.md). O setting `includeCoAuthoredBy:false` do Claude Code **não basta**: o
modelo escreve o trailer À MÃO no `git commit -m` (Bash), e o setting só desliga o auto-append.
A garantia é determinística — um hook `commit-msg` que roda `strip_ai_trailers`. Co-autores
**humanos** reais são preservados; só a atribuição de **IA/ferramenta** sai.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# co-autor cujo autor é IA (Claude / noreply da Anthropic).
_AI_COAUTHOR = re.compile(r"^\s*co-authored-by:\s.*(claude|noreply@anthropic\.com)", re.IGNORECASE)
# rodapé de ferramenta ("🤖 Generated with [Claude Code]" e variantes).
_TOOL_FOOTER = re.compile(r"(generated with .*claude|🤖 generated with)", re.IGNORECASE)


def strip_ai_trailers(message: str) -> str:
    """Remove co-autor de IA e rodapé de ferramenta; preserva o resto (co-autor humano)."""
    kept = [
        line
        for line in message.splitlines()
        if not _AI_COAUTHOR.match(line) and not _TOOL_FOOTER.search(line)
    ]
    while kept and not kept[-1].strip():  # tira linhas em branco sobrando no fim
        kept.pop()
    return "\n".join(kept) + ("\n" if message.endswith("\n") else "")


_HOOK = (
    "#!/bin/sh\n"
    'command -v python >/dev/null 2>&1 && python -m roboto.app.commit_hygiene "$1"\n'
    "exit 0\n"
)


def install_hook(home: str | None = None) -> str:
    """Instala o hook `commit-msg` GLOBAL (`core.hooksPath`) que roda `strip_ai_trailers` em todo
    commit — inclusive os do motor no repo-alvo (pega o trailer manual que o setting não barra).
    Idempotente. Devolve o caminho dos hooks."""
    base = home or os.path.expanduser("~")
    hooks = os.path.join(base, ".roboto-git-hooks")
    os.makedirs(hooks, exist_ok=True)
    path = os.path.join(hooks, "commit-msg")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_HOOK)
    os.chmod(path, 0o755)  # noqa: S103 — hook precisa ser executável
    subprocess.run(["git", "config", "--global", "core.hooksPath", hooks], check=False)  # noqa: S607
    return hooks


def _main() -> int:
    """Hook `commit-msg`: reescreve o arquivo de mensagem (argv[1]) sem os trailers de IA."""
    if len(sys.argv) < 2:
        return 0
    path = sys.argv[1]
    with open(path, encoding="utf-8") as handle:
        original = handle.read()
    cleaned = strip_ai_trailers(original)
    if cleaned != original:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(cleaned)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
