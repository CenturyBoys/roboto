"""Modo setup (trilha O): helpers de config + app de setup (status/save + reload)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from roboto.config import config_status, missing_required, settable_from_env
from roboto.orchestrator.store import InMemoryStore
from roboto.web.setup import build_setup_app

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_TOKEN = "setup-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}
_FULL = {
    "ROBOTO_TENANT": "acme",
    "DATABASE_URL": "postgres://x",
    "ROBOTO_DEFAULT_REPO": "acme/app",
    "TELEGRAM_BOT_TOKEN": "bot",
    "OPENROUTER_API_KEY": "or",
    "GITHUB_API_TOKEN": "ghp",
}


def test_missing_required_and_status() -> None:
    assert "ROBOTO_TENANT" in missing_required({})
    assert "GITHUB_API_TOKEN" in missing_required({})  # falta auth do github
    assert missing_required(_FULL) == []  # completo
    st = config_status(_FULL)
    assert st["configured"] is True
    assert "OPENROUTER_API_KEY" in st["present"]  # type: ignore[operator]


def test_settable_from_env_ignores_bootstrap_and_empty() -> None:
    seed = settable_from_env({"ROBOTO_TENANT": "acme", "DATABASE_URL": "x", "ROBOTO_CHAT_ID": ""})
    assert seed == {"ROBOTO_TENANT": "acme"}  # DATABASE_URL é bootstrap; vazio é ignorado


def _setup_app(store: InMemoryStore, reload_event: asyncio.Event) -> httpx.AsyncClient:
    app = build_setup_app(
        store,
        token=_TOKEN,
        bootstrap={"DATABASE_URL": "postgres://x", "CONSOLE_TOKEN": _TOKEN},
        reload_event=reload_event,
        now=lambda: _T0,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://setup")


async def test_healthz_reports_setup_mode() -> None:
    store = InMemoryStore()
    async with _setup_app(store, asyncio.Event()) as c:
        body = (await c.get("/healthz")).json()
        assert body == {"ok": True, "mode": "setup"}


async def test_status_requires_token_and_reports_missing() -> None:
    store = InMemoryStore()
    async with _setup_app(store, asyncio.Event()) as c:
        assert (await c.get("/setup/status")).status_code == 401
        st = (await c.get("/setup/status", headers=_AUTH)).json()
        assert st["configured"] is False
        assert "ROBOTO_TENANT" in st["missing"]


async def test_save_persists_and_flips_configured_and_reloads() -> None:
    store = InMemoryStore()
    reload_event = asyncio.Event()
    async with _setup_app(store, reload_event) as c:
        # parcial: salva mas ainda não está completo
        partial = {"values": {"ROBOTO_TENANT": "acme"}}
        r1 = (await c.post("/setup", headers=_AUTH, json=partial)).json()
        assert r1["saved"] == ["ROBOTO_TENANT"] and r1["configured"] is False
        assert reload_event.is_set() is False
        # completa o resto (DATABASE_URL vem do bootstrap) -> configurado -> dispara reload
        rest = {k: v for k, v in _FULL.items() if k not in ("ROBOTO_TENANT", "DATABASE_URL")}
        r2 = (await c.post("/setup", headers=_AUTH, json={"values": rest})).json()
        assert r2["configured"] is True
        assert reload_event.is_set() is True
    stored = await store.get_app_config()
    assert stored["OPENROUTER_API_KEY"] == "or"  # persistiu no banco (origem: front)


async def test_save_ignores_non_settable_keys() -> None:
    store = InMemoryStore()
    async with _setup_app(store, asyncio.Event()) as c:
        await c.post("/setup", headers=_AUTH, json={"values": {"CONSOLE_TOKEN": "hack", "x": "y"}})
    assert await store.get_app_config() == {}  # bootstrap/desconhecidos não entram
