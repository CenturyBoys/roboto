"""Loop de correção dirigido por review (verifying→running, attempt++)."""

from __future__ import annotations

from roboto.agents.review import PullRequest, ReviewVerdict
from roboto.app.correction import correction_cycle


def _pr() -> PullRequest:
    return PullRequest(number=1, author="impl", title="feat: x", diff="+ x")


def _verdict(approved: bool, issues: list[str] | None = None) -> ReviewVerdict:
    return ReviewVerdict(approved=approved, issues=issues or [])


async def test_approved_first_try() -> None:
    calls = {"impl": 0}

    async def implement(feedback: list[str], forte: bool) -> PullRequest:
        calls["impl"] += 1
        return _pr()

    async def review(pr: PullRequest) -> ReviewVerdict:
        return _verdict(True)

    result = await correction_cycle(implement=implement, review=review)
    assert result.approved is True
    assert result.attempts == 1
    assert calls["impl"] == 1


async def test_approved_after_feedback() -> None:
    seen_feedback: list[list[str]] = []
    verdicts = [_verdict(False, ["sem teste"]), _verdict(False, ["nome ruim"]), _verdict(True)]

    async def implement(feedback: list[str], forte: bool) -> PullRequest:
        seen_feedback.append(list(feedback))
        return _pr()

    async def review(pr: PullRequest) -> ReviewVerdict:
        return verdicts.pop(0)

    result = await correction_cycle(implement=implement, review=review, max_attempts=3)
    assert result.approved is True
    assert result.attempts == 3
    # o feedback do review anterior chega na tentativa seguinte
    assert seen_feedback == [[], ["sem teste"], ["nome ruim"]]


async def test_gives_up_at_max_attempts() -> None:
    async def implement(feedback: list[str], forte: bool) -> PullRequest:
        return _pr()

    async def review(pr: PullRequest) -> ReviewVerdict:
        return _verdict(False, ["ainda com bug"])

    result = await correction_cycle(implement=implement, review=review, max_attempts=2)
    assert result.approved is False
    assert result.attempts == 2
    assert result.issues == ["ainda com bug"]  # pendências ficam para o humano


async def test_escada_ultima_tentativa_no_forte() -> None:
    # ESCADA (#1054): worker nas primeiras, GERENTE (forte=True) na ÚLTIMA antes do humano.
    fortes: list[bool] = []

    async def implement(feedback: list[str], forte: bool) -> PullRequest:
        fortes.append(forte)
        return _pr()

    async def review(pr: PullRequest) -> ReviewVerdict:
        return _verdict(False, ["x"])  # nunca aprova → vai até o teto

    await correction_cycle(implement=implement, review=review, max_attempts=3)
    assert fortes == [False, False, True]  # worker, worker, GERENTE


async def test_escada_gerente_salva_na_ultima() -> None:
    # o gerente (forte) aprova na última → NÃO escala pro humano.
    verdicts = [_verdict(False, ["x"]), _verdict(False, ["x"]), _verdict(True)]
    fortes: list[bool] = []

    async def implement(feedback: list[str], forte: bool) -> PullRequest:
        fortes.append(forte)
        return _pr()

    async def review(pr: PullRequest) -> ReviewVerdict:
        return verdicts.pop(0)

    r = await correction_cycle(implement=implement, review=review, max_attempts=3)
    assert r.approved is True and fortes[-1] is True  # fechou no gerente
