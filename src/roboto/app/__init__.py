"""Camada de composição: liga agentes, núcleo (outbox) e adapters."""

from roboto.app.compose import Adapters, build_adapters
from roboto.app.effects import GithubIssuePublisher, TelegramPublisher, TelegramQuestionPublisher
from roboto.app.engine_loop import TurnOutcome, drive_turn
from roboto.app.human import ReplyOutcome, handle_reply, request_human_input
from roboto.app.refine import refine_to_issue

__all__ = [
    "Adapters",
    "GithubIssuePublisher",
    "ReplyOutcome",
    "TelegramPublisher",
    "TelegramQuestionPublisher",
    "TurnOutcome",
    "build_adapters",
    "drive_turn",
    "handle_reply",
    "refine_to_issue",
    "request_human_input",
]
