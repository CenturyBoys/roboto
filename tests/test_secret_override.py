"""Override humano do secret-scan (#203, inc. B): store + ciclo libera + endpoint reenfileira."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from roboto.engines.port import EngineEvent, EngineEventKind
from roboto.engines.stub import StubEngine
from roboto.orchestrator.model import GithubEvent, RunState
from roboto.orchestrator.store import InMemoryStore
from roboto.web.console import build_console
from test_pr_cycle import _FakeGit, _FakeGithub, _run, _SeqGateway

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = "console-secret"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


async def test_store_secret_override_roundtrip() -> None:
    store = InMemoryStore()
    assert await store.is_secret_allowed(1) is False
    await store.allow_secret(1, _T0)
    assert await store.is_secret_allowed(1) is True
    assert await store.is_secret_allowed(2) is False  # por run


async def test_cycle_with_override_pushes_despite_leak() -> None:
    # B: com allow_secret, o scan positivo NÃO aborta — push segue e o override é auditado no feed.
    from roboto.app.pr_cycle import run_pr_cycle

    store = InMemoryStore()
    run = await _run(store)
    engine = StubEngine([EngineEvent(EngineEventKind.FINISHED)])
    git, github = _FakeGit(), _FakeGithub()
    git.diff_text = 'diff --git a/c.py b/c.py\n+TOKEN = "ghp_' + "a" * 36 + '"\n'  # sempre vaza
    result = await run_pr_cycle(
        engine=engine, gateway=_SeqGateway(["", ""]),  # type: ignore[arg-type]
        github=github, git=git, run=run, workdir="/work/acme/app",
        reviewer="review", store=store, now=_T0, allow_secret=True,
    )
    assert git.pushes  # empurrou apesar do segredo (override humano)
    assert github.opened == 1
    assert result.approved
    events = await store.session_events(run.id, 0, 50)
    assert any("OVERRIDE humano" in e.text for e in events)  # auditado


def _console(store: InMemoryStore, **kw: object) -> httpx.AsyncClient:
    app = build_console(store, tenant="acme", token=_TOKEN, **kw)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://console")


async def _failed_run(store: InMemoryStore) -> int:
    ev = GithubEvent(
        tenant="acme", repo="acme/app", issue_id="231", agent="impl", idempotency_key="k"
    )
    r, _ = await store.insert_run_if_absent(ev, _T0)
    await store.set_state(r.id, RunState.FAILED, _T0)
    return r.id


async def test_allow_secret_endpoint_sets_override_and_requeues() -> None:
    store = InMemoryStore()
    rid = await _failed_run(store)
    async with _console(store) as c:
        assert (await c.post(f"/executions/{rid}/allow-secret")).status_code == 401  # exige token
        r = await c.post(f"/executions/{rid}/allow-secret", headers=_AUTH)
        assert r.status_code == 200 and r.json()["state"] == str(RunState.QUEUED)
    assert await store.is_secret_allowed(rid) is True
    assert store._runs[rid].state is RunState.QUEUED  # type: ignore[attr-defined]


async def test_detail_flags_secret_blocked() -> None:
    store = InMemoryStore()
    rid = await _failed_run(store)
    await store.append_session_event(
        "acme", rid, "message", _T0, text="🔒 secret-scan bloqueou o push: possível segredo"
    )
    async with _console(store) as c:
        d = (await c.get(f"/executions/{rid}", headers=_AUTH)).json()
    assert d["secret_blocked"] is True
