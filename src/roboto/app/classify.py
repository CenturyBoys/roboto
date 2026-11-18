"""Classificação determinística de uma chamada de ferramenta (#267).

Dado `(tool, args)`, devolve `(ToolClass, ActionKinds, high_risk)` — o que a `verdict` (policy.py)
consome. O ganho sobre o `tool_policy` binário: **parsing de `Bash` por subcomando** — `git status`
é leitura, `git push` é a ação `push`; antes o `Bash` era tudo-ou-nada. `high_risk` reusa o
`jev_guard` (caminho sensível: migrations/CI/auth). Puro e sem I/O (o jev_guard só casa regex).
"""

from __future__ import annotations

import shlex

from roboto.app.jev_guard import assess
from roboto.app.policy import ActionKind, ToolClass

_READ_TOOLS = frozenset({"Read", "Grep", "Glob", "LS", "NotebookRead"})
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
# primeiro token de um comando que só LÊ/valida (não muda o repo nem publica).
_READ_CMDS = frozenset(
    {
        "ls", "cat", "pwd", "echo", "head", "tail", "grep", "rg", "find", "which", "wc",
        "diff", "stat", "env", "tree", "file", "pytest", "ruff", "mypy", "tsc", "eslint", "true",
    }
)
_GIT_READ = frozenset(
    {"status", "diff", "log", "show", "blame", "branch", "rev-parse", "fetch", "remote",
     "ls-files", "stash"}
)
_DELETE_CMDS = frozenset({"rm", "rmdir", "unlink", "shred"})


def _path_high_risk(path: str) -> bool:
    return bool(path) and assess([path]).escalate


def _bash(command: str) -> tuple[ToolClass, frozenset[ActionKind], bool]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return ToolClass.READ, frozenset(), False
    head, rest = tokens[0], tokens[1:]
    sub = rest[0] if rest else ""

    if head == "git":
        if sub == "commit":
            return ToolClass.WRITE, frozenset({ActionKind.COMMIT}), False
        if sub == "push":
            return ToolClass.WRITE, frozenset({ActionKind.PUSH}), False
        if sub == "merge":
            return ToolClass.WRITE, frozenset({ActionKind.MERGE}), False
        if sub == "clean":
            return ToolClass.WRITE, frozenset({ActionKind.DELETE}), "-f" in rest or "-fx" in rest
        if sub in _GIT_READ:
            return ToolClass.READ, frozenset(), False
        return ToolClass.WRITE, frozenset(), False  # add/reset/checkout: muda a árvore, não publica

    if head == "gh" and sub == "pr":
        action = rest[1] if len(rest) > 1 else ""
        if action == "merge":
            return ToolClass.WRITE, frozenset({ActionKind.MERGE}), False
        if action in {"create", "ready"}:
            return ToolClass.WRITE, frozenset({ActionKind.PR}), False
        return ToolClass.READ, frozenset(), False  # gh pr view/list/checks

    if head in _DELETE_CMDS:
        flags = {t for t in rest if t.startswith("-")}
        paths = [t for t in rest if not t.startswith("-")]
        dangerous = bool(flags & {"-rf", "-fr", "-r", "-f"}) or any(
            p in {"/", "~", "*"} or p.startswith("/") for p in paths
        )
        high = dangerous or any(_path_high_risk(p) for p in paths)
        return ToolClass.WRITE, frozenset({ActionKind.DELETE}), high

    if head in _READ_CMDS:
        return ToolClass.READ, frozenset(), False

    # bash desconhecido pode mudar estado → write (sob careful pede; não é sensitive p/ não gatear
    # todo comando de build/teste rotineiro).
    return ToolClass.WRITE, frozenset(), False


def classify(tool: str, args: dict[str, object]) -> tuple[ToolClass, frozenset[ActionKind], bool]:
    """Classe + ações + high_risk de uma chamada. MCP/desconhecida → leitura (navegação)."""
    if tool in _READ_TOOLS:
        return ToolClass.READ, frozenset(), False
    if tool in _WRITE_TOOLS:
        path = str(args.get("file_path", "") or args.get("notebook_path", "") or "")
        return ToolClass.WRITE, frozenset(), _path_high_risk(path)
    if tool == "Bash":
        return _bash(str(args.get("command", "") or ""))
    return ToolClass.READ, frozenset(), False
