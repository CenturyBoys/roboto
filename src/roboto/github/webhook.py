"""Ingest de webhook do GitHub App (inbound): valida assinatura -> normaliza -> ingest.

Lógica pura (sem servidor HTTP): o transporte ASGI é glue fino e entra depois. `tenant` vem do
servidor (qual app/instância recebeu), nunca do payload (D21). Assinatura HMAC-SHA256 obrigatória
(entrega é at-least-once → a idempotência do orquestrador cuida de duplicatas).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime

from roboto.orchestrator.core import ingest
from roboto.orchestrator.model import Error, GithubEvent, Run
from roboto.orchestrator.store import Store
from roboto.result import Err, Ok, Result

# evento GitHub -> (ação relevante -> agente). Evento/ação fora disso é ignorado (202).
_PR_ACTIONS = {"opened": "review", "synchronize": "review", "reopened": "review"}


def verify_signature(secret: str, body: bytes, signature_header: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def normalize_event(
    event_type: str, payload: dict[str, object], tenant: str
) -> Result[GithubEvent | None, Error]:
    """Mapeia evento do GitHub para `GithubEvent`. Evento não-acionável → `Ok(None)`."""
    try:
        if event_type == "issues" and payload.get("action") == "opened":
            repo = _repo(payload)
            number = str(_issue_number(payload))
            return Ok[GithubEvent | None](
                GithubEvent(
                    tenant=tenant,
                    repo=repo,
                    issue_id=number,
                    agent="triage",
                    idempotency_key=f"issues:opened:{repo}:{number}",
                )
            )
        if event_type == "pull_request":
            action = str(payload.get("action", ""))
            agent = _PR_ACTIONS.get(action)
            if agent is None:
                return Ok[GithubEvent | None](None)
            repo = _repo(payload)
            pr = _pull_request(payload)
            number = str(pr["number"])
            head = pr["head"]
            assert isinstance(head, dict)
            head_sha = str(head["sha"])
            return Ok[GithubEvent | None](
                GithubEvent(
                    tenant=tenant,
                    repo=repo,
                    issue_id=number,
                    agent=agent,
                    idempotency_key=f"pull_request:{action}:{repo}:{number}:{head_sha}",
                )
            )
    except (KeyError, TypeError) as exc:
        return Err(Error("invalid", f"payload {event_type} malformado: {exc}"))
    return Ok[GithubEvent | None](None)


async def handle_webhook(
    *,
    secret: str,
    tenant: str,
    event_type: str,
    signature: str,
    body: bytes,
    store: Store,
    now: datetime,
) -> Result[Run | None, Error]:
    if not verify_signature(secret, body, signature):
        return Err(Error("invalid_signature", "assinatura do webhook inválida"))
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Err(Error("invalid", "payload não-JSON"))
    normalized = normalize_event(event_type, payload, tenant)
    if isinstance(normalized, Err):
        return Err(normalized.error)
    event = normalized.value
    if event is None:
        return Ok[Run | None](None)  # ignorado (202)
    ingested = await ingest(store, event, now)
    if isinstance(ingested, Err):
        return Err(ingested.error)
    return Ok[Run | None](ingested.value)


def _repo(payload: dict[str, object]) -> str:
    repository = payload["repository"]
    assert isinstance(repository, dict)
    return str(repository["full_name"])


def _issue_number(payload: dict[str, object]) -> int:
    issue = payload["issue"]
    assert isinstance(issue, dict)
    return int(issue["number"])


def _pull_request(payload: dict[str, object]) -> dict[str, object]:
    pr = payload["pull_request"]
    assert isinstance(pr, dict)
    return pr
