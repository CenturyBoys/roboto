"""Camada de composição: liga agentes, núcleo (outbox) e adapters."""

from roboto.app.effects import GithubIssuePublisher, TelegramPublisher
from roboto.app.refine import refine_to_issue

__all__ = ["GithubIssuePublisher", "TelegramPublisher", "refine_to_issue"]
