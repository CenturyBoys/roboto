"""App ASGI combinado (webhook + console) via httpx.ASGITransport."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx

from roboto.config import load_config
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Ok
from roboto.web.app import build_app

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_ENV = {
    "ROBOTO_TENANT": "acme",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/roboto",
    "ROBOTO_DEFAULT_REPO": "acme/app",
    "GITHUB_APP_ID": "123",
    "GITHUB_APP_PRIVATE_KEY": "x",
    "GITHUB_APP_INSTALLATION_ID": "789",
    "GITHUB_WEBHOOK_SECRET": "whsec",
    "TELEGRAM_BOT_TOKEN": "000:AAA",
    "OPENROUTER_API_KEY": "sk-or",
    "STT_API_KEY": "sk",
    "CONSOLE_TOKEN": "ctok",
}


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"whsec", body, hashlib.sha256).hexdigest()


def _app(store: InMemoryStore) -> httpx.AsyncClient:
    cfg = load_config(_ENV)
    assert isinstance(cfg, Ok)
    app = build_app(store, config=cfg.value, now=lambda: _T0)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roboto")


async def test_webhook_accepts_signed_issue() -> None:
    store = InMemoryStore()
    async with _app(store) as c:
        body = json.dumps(
            {
                "action": "opened",
                "repository": {"full_name": "acme/app"},
                "issue": {"number": 42, "labels": [{"name": "roboto"}]},  # opt-in (D29)
            }
        ).encode()
        resp = await c.post(
            "/webhook",
            content=body,
            headers={"x-github-event": "issues", "x-hub-signature-256": _sign(body)},
        )
        assert resp.status_code == 202
        assert resp.json()["run_id"] is not None


async def test_webhook_bad_signature_401() -> None:
    store = InMemoryStore()
    async with _app(store) as c:
        resp = await c.post(
            "/webhook",
            content=b'{"action":"opened"}',
            headers={"x-github-event": "issues", "x-hub-signature-256": "sha256=wrong"},
        )
        assert resp.status_code == 401


async def test_console_shares_same_app() -> None:
    store = InMemoryStore()
    async with _app(store) as c:
        assert (await c.get("/healthz")).status_code == 200
        assert (await c.get("/executions")).status_code == 401
        ok = await c.get("/executions", headers={"Authorization": "Bearer ctok"})
        assert ok.status_code == 200
