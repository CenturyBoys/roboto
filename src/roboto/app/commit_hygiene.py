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


# linha do hook: SELF-CONTAINED (grep puro) — NÃO importa roboto (o motor commita em /work, onde o
# pacote não está no path; era por isso que o stripper não rodava mesmo instalado). Mesma regra do
# `strip_ai_trailers`: remove co-autor de IA (claude/anthropic) + rodapé de ferramenta.
_STRIP = (
    "grep -viE "
    "'^[[:space:]]*co-authored-by:.*(claude|noreply@anthropic\\.com)"
    "|generated with .*claude|🤖 generated with' "
    '"$1" > "$1.hyg" 2>/dev/null && mv "$1.hyg" "$1"\n'
)
_HOOK = "#!/bin/sh\n" + _STRIP + "exit 0\n"


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


def install_repo_hook(repo_dir: str) -> str:
    """Instala o stripper como `commit-msg` no hooks path EFETIVO do repo-alvo. Necessário porque um
    repo pode setar `core.hooksPath` LOCAL (ex.: `.githooks` via `prepare`/pnpm) que **override** o
    nosso hook GLOBAL — foi o deslize do #323 (o `.githooks` do alvo só tinha `pre-commit`, então o
    trailer passava). Encadeia um `commit-msg` já existente. Idempotente; devolve o caminho."""
    # Onde o repo VAI procurar os hooks (prioridade, resolve o timing do #323):
    # 1) core.hooksPath LOCAL já setado (o override do próprio repo); senão
    # 2) um dir `.githooks` versionado (convenção que o `prepare`/pnpm ativa DEPOIS — instala lá
    #    p/ sobreviver ao override); senão 3) o default `.git/hooks`.
    # Lê o LOCAL (não o efetivo): o global é o nosso hook separado (instalaria no lugar errado).
    res = subprocess.run(  # noqa: S603,S607 — comando fixo
        ["git", "-C", repo_dir, "config", "--local", "core.hooksPath"],
        capture_output=True, text=True,
    )
    rel = res.stdout.strip()
    if rel:
        hooks_dir = os.path.join(repo_dir, rel)
    elif os.path.isdir(os.path.join(repo_dir, ".githooks")):
        hooks_dir = os.path.join(repo_dir, ".githooks")
    else:
        hooks_dir = os.path.join(repo_dir, ".git", "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    target = os.path.join(hooks_dir, "commit-msg")
    chain = ""
    if os.path.exists(target) and "$1.hyg" not in open(target, encoding="utf-8").read():
        saved = target + ".repo"  # preserva o commit-msg do repo e o roda ANTES do stripper
        if not os.path.exists(saved):
            os.rename(target, saved)
        os.chmod(saved, 0o755)  # noqa: S103
        chain = 'd=$(dirname "$0"); "$d/commit-msg.repo" "$1" || exit $?\n'
    hook = "#!/bin/sh\n" + chain + _STRIP + "exit 0\n"
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(hook)
    os.chmod(target, 0o755)  # noqa: S103 — hook precisa ser executável
    return target


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
