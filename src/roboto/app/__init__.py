"""Camada de composição: liga agentes, núcleo (outbox) e adapters."""

from roboto.app.compose import Adapters, build_adapters
from roboto.app.effects import GithubIssuePublisher, TelegramPublisher, TelegramQuestionPublisher
from roboto.app.engine_loop import TurnOutcome, drive_turn
from roboto.app.human import ReplyOutcome, handle_reply, request_human_input
from roboto.app.inbound import InboundOutcome, dispatch_inbound
from roboto.app.loops import poll_tick, process_run_tick, run_periodic
from roboto.app.refine import refine_to_issue

__all__ = [
    "Adapters",
    "GithubIssuePublisher",
    "InboundOutcome",
    "ReplyOutcome",
    "TelegramPublisher",
    "TelegramQuestionPublisher",
    "TurnOutcome",
    "build_adapters",
    "dispatch_inbound",
    "drive_turn",
    "handle_reply",
    "poll_tick",
    "process_run_tick",
    "refine_to_issue",
    "request_human_input",
    "run_periodic",
]
