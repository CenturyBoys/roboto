"""Testes do runner de migrations no boot (#276, app pura)."""

from __future__ import annotations

from roboto.orchestrator.migrate import pending_migrations


def test_pending_returns_unapplied_in_lexical_order() -> None:
    files = ["0002_b.sql", "0001_a.sql", "0003_c.sql"]
    assert pending_migrations(files, {"0001_a.sql"}) == ["0002_b.sql", "0003_c.sql"]


def test_pending_empty_when_all_applied() -> None:
    files = ["0001_a.sql", "0002_b.sql"]
    assert pending_migrations(files, {"0001_a.sql", "0002_b.sql"}) == []


def test_pending_all_when_none_applied() -> None:
    files = ["0002_b.sql", "0001_a.sql"]
    assert pending_migrations(files, set()) == ["0001_a.sql", "0002_b.sql"]
