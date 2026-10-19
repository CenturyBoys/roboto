"""Adapter do GitHub App (identidade do fleet; N repos por org — D17/D21)."""

from roboto.github.app import GithubAppClient, IssueRef
from roboto.github.webhook import handle_webhook, normalize_event, verify_signature

__all__ = [
    "GithubAppClient",
    "IssueRef",
    "handle_webhook",
    "normalize_event",
    "verify_signature",
]
