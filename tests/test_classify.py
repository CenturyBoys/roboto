"""Testes do classificador de chamadas (#267, app.classify)."""

from __future__ import annotations

from roboto.app.classify import classify
from roboto.app.policy import ActionKind, ToolClass


def test_read_tools_are_read() -> None:
    cls, kinds, high = classify("Read", {"file_path": "a.py"})
    assert cls is ToolClass.READ
    assert not kinds
    assert not high


def test_bash_git_status_is_read_but_push_is_push() -> None:
    assert classify("Bash", {"command": "git status"}) == (ToolClass.READ, frozenset(), False)
    cls, kinds, _ = classify("Bash", {"command": "git push origin main"})
    assert cls is ToolClass.WRITE
    assert kinds == frozenset({ActionKind.PUSH})


def test_bash_git_commit_and_gh_pr_merge() -> None:
    _, kinds_commit, _ = classify("Bash", {"command": "git commit -m x"})
    assert kinds_commit == frozenset({ActionKind.COMMIT})
    _, kinds_merge, _ = classify("Bash", {"command": "gh pr merge 42 --squash"})
    assert kinds_merge == frozenset({ActionKind.MERGE})


def test_bash_rm_is_delete_and_dangerous_is_high_risk() -> None:
    cls, kinds, high = classify("Bash", {"command": "rm -rf build"})
    assert cls is ToolClass.WRITE
    assert kinds == frozenset({ActionKind.DELETE})
    assert high


def test_edit_sensitive_path_is_high_risk() -> None:
    _, _, high_sensitive = classify("Edit", {"file_path": "migrations/0014_x.sql"})
    _, _, high_normal = classify("Edit", {"file_path": "src/roboto/app/foo.py"})
    assert high_sensitive
    assert not high_normal


def test_unknown_mcp_tool_is_read() -> None:
    cls, kinds, _ = classify("mcp__code-intel__find_references", {"symbol": "x"})
    assert cls is ToolClass.READ
    assert not kinds
