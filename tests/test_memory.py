"""Recall do second brain pra injeção em prompt (Trilha G)."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.memory import recall_block
from roboto.orchestrator.store import InMemoryStore

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def test_recall_block_empty_when_no_facts() -> None:
    store = InMemoryStore()
    assert await recall_block(store, "acme", "qualquer coisa") == ""


async def test_recall_block_formats_relevant_facts() -> None:
    store = InMemoryStore()
    await store.remember("acme", "usar Result, não exceção", kind="decisao", ref="", now=_T0)
    csv = "o export de CSV usa ponto-e-vírgula"
    await store.remember("acme", csv, kind="fato", ref="", now=_T0)
    await store.remember("acme", "nada a ver com isso", kind="fato", ref="", now=_T0)
    block = await recall_block(store, "acme", "export de CSV")
    assert "[fato] o export de CSV usa ponto-e-vírgula" in block
    assert "nada a ver" not in block  # só o relevante


async def test_recall_block_is_capped() -> None:
    store = InMemoryStore()
    for i in range(20):
        await store.remember("acme", "export " + "x" * 300, kind="fato", ref=str(i), now=_T0)
    block = await recall_block(store, "acme", "export", max_chars=400)
    assert len(block) <= 410 and block.endswith("…")


async def test_recall_block_isolates_tenant() -> None:
    store = InMemoryStore()
    await store.remember("acme", "segredo do acme sobre export", kind="fato", ref="", now=_T0)
    assert await recall_block(store, "outra", "export") == ""
