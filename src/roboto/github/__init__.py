"""Adapter do GitHub App (identidade do fleet; N repos por org — D17/D21)."""

from roboto.github.app import GithubAppClient, IssueRef

__all__ = ["GithubAppClient", "IssueRef"]
