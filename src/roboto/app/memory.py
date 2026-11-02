"""Recall do second brain pra injeção em prompt (Trilha G).

Memória = **fatos versionados** (storage, fonte da verdade) + **recall determinístico** (o PgStore
usa FTS/`ts_rank`; o InMemory, overlap de termos) — SEM LLM pra recuperar (barato, trilha F).

Este helper recalla os fatos relevantes e devolve um bloco pronto pra injetar no prompt, **capado**
por orçamento de token. Mesma régua de E/F: o HARNESS injeta a continuidade (decisões/convenções/
fixes) em vez de depender do modelo lembrar — continuidade entre runs sem sessão gigante.
"""

from __future__ import annotations

from roboto.orchestrator.store import Store

_MEMORY_MAX_CHARS = 1500  # teto de token: memória é contexto de apoio, não o grosso do prompt


async def recall_block(
    store: Store, tenant: str, query: str, *, limit: int = 5, max_chars: int = _MEMORY_MAX_CHARS
) -> str:
    """Recalla os fatos relevantes pra `query` e formata um bloco capado. Vazio se não há nada."""
    facts = await store.recall(tenant, query, limit)
    if not facts:
        return ""
    block = "\n".join(f"- [{f.kind}] {f.text}" for f in facts)
    if len(block) > max_chars:
        block = block[:max_chars].rstrip() + " …"
    return block
