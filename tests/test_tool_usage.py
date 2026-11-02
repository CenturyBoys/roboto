"""Telemetria de ferramentas (Trilha F): categorização e eficiência semântica."""

from __future__ import annotations

from roboto.app.tool_usage import categorize_tool, summarize


def test_categorize_code_intel_is_semantic() -> None:
    assert categorize_tool("mcp__code-intel__find_references") == "semantic"
    assert categorize_tool("mcp__code-intel__rename_symbol") == "semantic"
    assert categorize_tool("mcp__code_intel__workspace_symbols") == "semantic"


def test_categorize_builtins() -> None:
    assert categorize_tool("Read") == "read_full"
    assert categorize_tool("Grep") == "search"
    assert categorize_tool("Glob") == "search"
    assert categorize_tool("Edit") == "edit"
    assert categorize_tool("Write") == "edit"
    assert categorize_tool("Bash") == "shell"
    assert categorize_tool("WebFetch") == "other"


def test_summarize_counts_by_category() -> None:
    u = summarize(
        {
            "mcp__code-intel__find_references": 3,
            "Read": 1,
            "Grep": 2,
            "Edit": 1,
            "Bash": 4,
        }
    )
    assert u.total == 11
    assert u.by_category["semantic"] == 3
    assert u.by_category["read_full"] == 1
    assert u.by_category["search"] == 2
    assert u.by_category["edit"] == 1
    assert u.by_category["shell"] == 4
    assert u.by_category["other"] == 0


def test_efficiency_is_semantic_over_navigation() -> None:
    # 3 semânticas + 1 Read => 3/4 = 0.75 (olhar código pelo caminho barato)
    u = summarize({"mcp__code-intel__find_references": 3, "Read": 1})
    assert u.efficiency == 0.75


def test_efficiency_none_when_no_navigation() -> None:
    # só edição/shell: não dá pra opinar sobre navegação
    u = summarize({"Edit": 2, "Bash": 1})
    assert u.efficiency is None


def test_efficiency_zero_when_only_whole_file_reads() -> None:
    u = summarize({"Read": 5})
    assert u.efficiency == 0.0


def test_empty_is_zeroed() -> None:
    u = summarize({})
    assert u.total == 0
    assert u.efficiency is None
    assert set(u.by_category) == {"semantic", "read_full", "search", "edit", "shell", "other"}
