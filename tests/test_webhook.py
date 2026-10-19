"""Ingest de webhook do GitHub (assinatura + normalização + ingest idempotente)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

from roboto.github.webhook import handle_webhook, normalize_event, verify_signature
from roboto.orchestrator.store import InMemoryStore
from roboto.result import Err, Ok

_SECRET = "whsec"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_roundtrip() -> None:
    body = b'{"a":1}'
    assert verify_signature(_SECRET, body, _sign(body)) is True
    assert verify_signature(_SECRET, body, "sha256=deadbeef") is False
    assert verify_signature(_SECRET, body, "md5=x") is False


def test_normalize_issue_opened() -> None:
    payload: dict[str, object] = {
        "action": "opened",
        "repository": {"full_name": "acme/app"},
        "issue": {"number": 42},
    }
    result = normalize_event("issues", payload, "acme")
    assert isinstance(result, Ok)
    ev = result.value
    assert ev is not None
    assert ev.repo == "acme/app"
    assert ev.issue_id == "42"
    assert ev.agent == "triage"
    assert ev.idempotency_key == "issues:opened:acme/app:42"


def test_normalize_pull_request_opened() -> None:
    payload: dict[str, object] = {
        "action": "opened",
        "repository": {"full_name": "acme/app"},
        "pull_request": {"number": 7, "head": {"sha": "abc123"}},
    }
    result = normalize_event("pull_request", payload, "acme")
    assert isinstance(result, Ok)
    assert result.value is not None
    assert result.value.agent == "review"
    assert result.value.idempotency_key == "pull_request:opened:acme/app:7:abc123"


def test_normalize_ignored_event_is_none() -> None:
    assert normalize_event("issues", {"action": "labeled"}, "acme").value is None  # type: ignore[union-attr]
    assert normalize_event("star", {}, "acme").value is None  # type: ignore[union-attr]


async def test_handle_webhook_ingests_run() -> None:
    store = InMemoryStore()
    payload = {
        "action": "opened",
        "repository": {"full_name": "acme/app"},
        "issue": {"number": 42},
    }
    body = json.dumps(payload).encode()
    result = await handle_webhook(
        secret=_SECRET,
        tenant="acme",
        event_type="issues",
        signature=_sign(body),
        body=body,
        store=store,
        now=_T0,
    )
    assert isinstance(result, Ok)
    assert result.value is not None
    assert result.value.repo == "acme/app"
    # idempotência: reenvio do mesmo evento não cria outro run
    again = await handle_webhook(
        secret=_SECRET,
        tenant="acme",
        event_type="issues",
        signature=_sign(body),
        body=body,
        store=store,
        now=_T0,
    )
    assert isinstance(again, Ok)
    assert again.value is not None
    assert again.value.id == result.value.id


async def test_handle_webhook_bad_signature_is_err() -> None:
    store = InMemoryStore()
    body = b'{"action":"opened"}'
    result = await handle_webhook(
        secret=_SECRET,
        tenant="acme",
        event_type="issues",
        signature="sha256=wrong",
        body=body,
        store=store,
        now=_T0,
    )
    assert isinstance(result, Err)
    assert result.error.kind == "invalid_signature"


async def test_handle_webhook_ignored_event_returns_none() -> None:
    store = InMemoryStore()
    body = json.dumps({"action": "deleted"}).encode()
    result = await handle_webhook(
        secret=_SECRET,
        tenant="acme",
        event_type="issues",
        signature=_sign(body),
        body=body,
        store=store,
        now=_T0,
    )
    assert isinstance(result, Ok)
    assert result.value is None
