"""Loop de correção dirigido por review (D28, trilha D + máquina de estados do orquestrador).

Materializa `verifying → running (attempt++)`: implementa → review → se reprovado, re-implementa
usando os comentários do review como feedback → re-review, até aprovar ou estourar o teto.
`implement`/`review` são injetados (o real: `drive_turn`+GitHub e `review_pr` com reviewer≠autor);
aqui o loop é puro e determinístico. Aprovação NÃO mergeia — o merge tem gate humano (D7).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from roboto.agents.review import PullRequest, ReviewVerdict


@dataclass(frozen=True)
class CycleResult:
    approved: bool
    attempts: int
    pr: PullRequest | None = None
    issues: list[str] = field(default_factory=list)  # pendências se não aprovou


async def correction_cycle(
    *,
    implement: Callable[[list[str]], Awaitable[PullRequest]],
    review: Callable[[PullRequest], Awaitable[ReviewVerdict]],
    max_attempts: int = 3,
) -> CycleResult:
    """implement(feedback)->PR; review(PR)->veredito. Realimenta até aprovar ou estourar o teto."""
    feedback: list[str] = []
    pr: PullRequest | None = None
    for attempt in range(1, max_attempts + 1):
        pr = await implement(feedback)  # 1ª vez sem feedback; depois com os problemas do review
        verdict = await review(pr)
        if verdict.approved:
            return CycleResult(approved=True, attempts=attempt, pr=pr)
        feedback = verdict.issues
    return CycleResult(approved=False, attempts=max_attempts, pr=pr, issues=feedback)
