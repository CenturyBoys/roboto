"""Camada de composição: liga agentes, núcleo (outbox) e adapters."""

from roboto.app.compose import Adapters, build_adapters
from roboto.app.effects import GithubIssuePublisher, TelegramPublisher
from roboto.app.refine import refine_to_issue

__all__ = [
    "Adapters",
    "GithubIssuePublisher",
    "TelegramPublisher",
    "build_adapters",
    "refine_to_issue",
]
