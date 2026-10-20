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


def _is_for_fleet(obj: dict[str, object], trigger_label: str, bot_login: str) -> bool:
    """Opt-in: o fleet só age se a issue/PR tem o label-gatilho OU está atribuída ao bot.

    Sem label/bot configurados -> reage a tudo (compat). Com gente trabalhando junto, configure
    `trigger_label` (ex.: 'roboto') e/ou `bot_login` para NÃO mexer no que não é do fleet.
    """
    if not trigger_label and not bot_login:
        return True
    labels = obj.get("labels", [])
    names = (
        {x.get("name") for x in labels if isinstance(x, dict)}
        if isinstance(labels, list)
        else set()
    )
    assignees = obj.get("assignees", [])
    logins = (
        {x.get("login") for x in assignees if isinstance(x, dict)}
        if isinstance(assignees, list)
        else set()
    )
    return (bool(trigger_label) and trigger_label in names) or (
        bool(bot_login) and bot_login in logins
    )


def normalize_event(
    event_type: str,
    payload: dict[str, object],
    tenant: str,
    *,
    trigger_label: str = "",
    bot_login: str = "",
) -> Result[GithubEvent | None, Error]:
    """Mapeia evento do GitHub para `GithubEvent`. Não-acionável / não-do-fleet → `Ok(None)`."""
    try:
        if event_type == "issues" and payload.get("action") == "opened":
            issue = payload["issue"]
            assert isinstance(issue, dict)
            if not _is_for_fleet(issue, trigger_label, bot_login):
                return Ok[GithubEvent | None](None)  # issue de humano, sem gatilho -> ignora
            repo = _repo(payload)
            number = str(issue["number"])
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
            pr = _pull_request(payload)
            if not _is_for_fleet(pr, trigger_label, bot_login):
                return Ok[GithubEvent | None](None)  # PR de humano, sem gatilho -> ignora
            repo = _repo(payload)
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
    repos: frozenset[str] = frozenset(),
    trigger_label: str = "",
    bot_login: str = "",
) -> Result[Run | None, Error]:
    if not verify_signature(secret, body, signature):
        return Err(Error("invalid_signature", "assinatura do webhook inválida"))
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Err(Error("invalid", "payload não-JSON"))
    normalized = normalize_event(
        event_type, payload, tenant, trigger_label=trigger_label, bot_login=bot_login
    )
    if isinstance(normalized, Err):
        return Err(normalized.error)
    event = normalized.value
    if event is None:
        return Ok[Run | None](None)  # ignorado (202)
    if repos and event.repo not in repos:
        return Ok[Run | None](None)  # repo fora do escopo desta instância (D17)
    ingested = await ingest(store, event, now)
    if isinstance(ingested, Err):
        return Err(ingested.error)
    return Ok[Run | None](ingested.value)


def _repo(payload: dict[str, object]) -> str:
    repository = payload["repository"]
    assert isinstance(repository, dict)
    return str(repository["full_name"])


def _pull_request(payload: dict[str, object]) -> dict[str, object]:
    pr = payload["pull_request"]
    assert isinstance(pr, dict)
    return pr
