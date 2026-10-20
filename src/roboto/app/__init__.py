"""Camada de composição: liga agentes, núcleo (outbox) e adapters."""

from roboto.app.compose import Adapters, build_adapters
from roboto.app.correction import CycleResult, correction_cycle
from roboto.app.effects import GithubIssuePublisher, TelegramPublisher, TelegramQuestionPublisher
from roboto.app.engine_loop import TurnOutcome, drive_turn
from roboto.app.git_ops import SubprocessGit
from roboto.app.human import ReplyOutcome, handle_reply, request_human_input
from roboto.app.inbound import InboundOutcome, dispatch_inbound
from roboto.app.loops import poll_tick, process_run_tick, run_periodic
from roboto.app.pr_cycle import GithubPrOps, GitOps, process_pr_run_tick, run_pr_cycle
from roboto.app.refine import refine_to_issue

__all__ = [
    "Adapters",
    "CycleResult",
    "GitOps",
    "GithubIssuePublisher",
    "GithubPrOps",
    "SubprocessGit",
    "InboundOutcome",
    "ReplyOutcome",
    "TelegramPublisher",
    "TelegramQuestionPublisher",
    "TurnOutcome",
    "build_adapters",
    "correction_cycle",
    "dispatch_inbound",
    "drive_turn",
    "handle_reply",
    "poll_tick",
    "process_pr_run_tick",
    "process_run_tick",
    "refine_to_issue",
    "request_human_input",
    "run_periodic",
    "run_pr_cycle",
]
