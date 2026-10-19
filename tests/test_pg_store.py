"""Integração do PostgresStore contra um Postgres real.

Pula sozinho se ``asyncpg`` não estiver instalado ou ``DATABASE_URL`` não estiver no ambiente
(local: `docker compose up`; CI: serviço postgres). Mesmos cenários do store em memória, agora
validando o SQL de verdade (idempotência, claim+lock, outbox, lease/abandono).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

asyncpg = pytest.importorskip("asyncpg")
import pytest_asyncio  # noqa: E402

from roboto.orchestrator.model import GithubEvent, RunState  # noqa: E402
from roboto.orchestrator.pg_store import PostgresStore  # noqa: E402

DSN = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN, reason="DATABASE_URL não definido (sobe via docker compose / CI)"
)

_MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0001_init.sql"
_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _event(key: str = "k1") -> GithubEvent:
    return GithubEvent(
        tenant="acme", repo="acme/app", issue_id="42", agent="impl", idempotency_key=key
    )


@pytest_asyncio.fixture
async def store() -> PostgresStore:
    pool = await asyncpg.create_pool(DSN)
    async with pool.acquire() as conn:
        await conn.execute(_MIGRATION.read_text())
        await conn.execute("TRUNCATE run, run_event, outbox, llm_call RESTART IDENTITY CASCADE")
    s = PostgresStore(pool)
    yield s
    await s.close()


async def test_insert_run_if_absent_is_idempotent(store: PostgresStore) -> None:
    run1, created1 = await store.insert_run_if_absent(_event(), _T0)
    run2, created2 = await store.insert_run_if_absent(_event(), _T0)
    assert created1 is True
    assert created2 is False
    assert run1.id == run2.id
    assert run1.state is RunState.QUEUED


async def test_claim_transitions_to_running_once(store: PostgresStore) -> None:
    await store.insert_run_if_absent(_event(), _T0)
    claimed = await store.claim_next_queued("acme", _T0, 300)
    assert claimed is not None
    assert claimed.state is RunState.RUNNING
    assert claimed.lease_until == _T0 + timedelta(seconds=300)
    # fila vazia depois do claim (lock + transição atômica)
    assert await store.claim_next_queued("acme", _T0, 300) is None
    await store.set_state(claimed.id, RunState.VERIFYING, _T0)
    assert await store.find_abandoned(_T0 + timedelta(hours=1)) == []


async def test_outbox_dedup_pending_and_mark_sent(store: PostgresStore) -> None:
    run, _ = await store.insert_run_if_absent(_event(), _T0)
    ok1 = await store.enqueue_effect("acme", run.id, "open_pr", {"n": 1}, "dk-1", _T0)
    ok2 = await store.enqueue_effect("acme", run.id, "open_pr", {"n": 1}, "dk-1", _T0)
    assert ok1 is True
    assert ok2 is False  # dedup por (tenant, dedup_key)
    pending = await store.pending_effects(10)
    assert len(pending) == 1
    assert pending[0].payload == {"n": 1}
    await store.mark_sent(pending[0].id, _T0)
    assert await store.pending_effects(10) == []


async def test_find_abandoned_after_lease_expires(store: PostgresStore) -> None:
    await store.insert_run_if_absent(_event(), _T0)
    claimed = await store.claim_next_queued("acme", _T0, 300)
    assert claimed is not None
    abandoned = await store.find_abandoned(_T0 + timedelta(seconds=400))
    assert [r.id for r in abandoned] == [claimed.id]
