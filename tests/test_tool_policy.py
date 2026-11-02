"""Least privilege por tipo de agente (Trilha H)."""

from __future__ import annotations

import pytest

from roboto.app.tool_policy import disallowed_tools_for


@pytest.mark.parametrize("agent", ["refine", "scope", "review"])
def test_read_only_agents_cannot_mutate(agent: str) -> None:
    blocked = disallowed_tools_for(agent)
    assert set(blocked) == {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}


@pytest.mark.parametrize("agent", ["impl", "implement", "correct", "desconhecido"])
def test_implementers_are_unrestricted(agent: str) -> None:
    assert disallowed_tools_for(agent) == []


def test_read_only_keeps_navigation_tools_allowed() -> None:
    # Read/Grep/Glob e code-intel NÃO entram na lista de negados — navegação segue liberada (F).
    blocked = disallowed_tools_for("refine")
    for navegacao in ("Read", "Grep", "Glob", "mcp__code-intel__find_references"):
        assert navegacao not in blocked
