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


async def test_remember_unique_by_ref_dedup() -> None:
    # Fatia 1: perfil/decisão com unique_by_ref mantém só 1 vigente por (kind, ref) — não acumula
    store = InMemoryStore()
    for i in range(3):
        await store.remember(
            "acme", f"perfil v{i}", kind="perfil", ref="acme/app", now=_T0, unique_by_ref=True
        )
    facts = [f for f in store._facts if f.kind == "perfil"]  # type: ignore[attr-defined]
    assert len(facts) == 1 and facts[0].text == "perfil v2"  # só o último sobrevive


async def test_remember_unique_by_ref_nao_afeta_outros_ref_ou_kind() -> None:
    store = InMemoryStore()
    u = {"now": _T0, "unique_by_ref": True}
    await store.remember("acme", "perfil A", kind="perfil", ref="repoA", **u)
    await store.remember("acme", "perfil B", kind="perfil", ref="repoB", **u)
    await store.remember("acme", "decisão X", kind="decisão", ref="repoA", now=_T0)
    # refs/kinds distintos coexistem (dedup é só por (kind, ref))
    assert len(store._facts) == 3  # type: ignore[attr-defined]
