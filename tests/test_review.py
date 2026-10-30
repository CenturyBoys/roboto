"""Gate de prontidão da issue (DoR) — check_issue_readiness (determinístico)."""

from __future__ import annotations

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import (
    PullRequest,
    check_issue_readiness,
    review_issue_semantics,
    review_pr,
)
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.llm.stub import StubModelGateway
from roboto.orchestrator.model import Error
from roboto.result import Ok, Result

_READY_BODY = (
    "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] faz z\n"
    "## DoD\n- [ ] testes + CI\n## Fora de escopo\nnada"
)


def test_complete_issue_is_ready() -> None:
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=_READY_BODY))
    assert verdict.ready is True
    assert verdict.missing == []


def test_missing_sections_listed() -> None:
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body="## Contexto\nsó isso"))
    assert verdict.ready is False
    assert any("Escopo" in m for m in verdict.missing)
    assert any("Critérios de aceite" in m for m in verdict.missing)
    assert any("DoD" in m for m in verdict.missing)


def test_no_acceptance_checkbox_is_not_ready() -> None:
    # tem as seções mas nenhum item "- [ ]"
    body = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\nfaz z\n## DoD\ntestes"
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=body))
    assert verdict.ready is False
    assert any("- [ ]" in m for m in verdict.missing)


def test_empty_title_is_not_ready() -> None:
    verdict = check_issue_readiness(IssueDraft(title="  ", body=_READY_BODY))
    assert verdict.ready is False
    assert "título" in verdict.missing


# --- camada semântica da issue (juiz) ---
async def test_issue_semantics_approved() -> None:
    gw = StubModelGateway(reply="VEREDITO: aprovado\nPROBLEMAS:")
    result = await review_issue_semantics(IssueDraft(title="feat: x", body=_READY_BODY), gw)
    assert isinstance(result, Ok)
    assert result.value.approved is True


async def test_issue_semantics_rejected_lists_problems() -> None:
    gw = StubModelGateway(reply="VEREDITO: reprovado\nPROBLEMAS:\n- critério vago\n- escopo amplo")
    result = await review_issue_semantics(IssueDraft(title="feat: x", body=_READY_BODY), gw)
    assert isinstance(result, Ok)
    assert result.value.approved is False
    assert "critério vago" in result.value.issues


# --- review de PR (reviewer != autor) ---
def _pr(author: str = "impl") -> PullRequest:
    return PullRequest(number=7, author=author, title="feat: x", diff="+ código")


async def test_pr_review_blocks_self_review() -> None:
    gw = StubModelGateway(reply="VEREDITO: aprovado")  # não deve nem ser usado
    result = await review_pr(_pr(author="alice"), gw, reviewer="alice")
    assert isinstance(result, Ok)
    assert result.value.approved is False
    assert any("autor" in i for i in result.value.issues)


async def test_pr_review_approves_when_reviewer_differs() -> None:
    gw = StubModelGateway(reply="VEREDITO: aprovado\nPROBLEMAS:")
    result = await review_pr(_pr(author="alice"), gw, reviewer="bob")
    assert isinstance(result, Ok)
    assert result.value.approved is True


async def test_pr_review_requests_changes() -> None:
    gw = StubModelGateway(reply="VEREDITO: reprovado\nPROBLEMAS:\n- sem teste")
    result = await review_pr(_pr(author="alice"), gw, reviewer="bob")
    assert isinstance(result, Ok)
    assert result.value.approved is False
    assert "sem teste" in result.value.issues


class _CapturingGateway:
    """Gateway que guarda as mensagens recebidas, p/ inspecionar o prompt do review (ideia 1)."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.seen: list[ChatMessage] = []

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        self.seen = messages
        return Ok(Completion(text=self._reply, model="cap", tokens_in=0, tokens_out=0))


async def test_pr_review_injeta_achados_do_verify_no_prompt() -> None:
    gw = _CapturingGateway("VEREDITO: reprovado\nPROBLEMAS:\n- erro de tipo não tratado")
    achados = ["env.ts:226 Cannot find name 'process'."]
    result = await review_pr(_pr(author="alice"), gw, reviewer="bob", verify_findings=achados)
    assert isinstance(result, Ok)
    prompt_user = "\n".join(m.content for m in gw.seen if m.role == "user")
    assert "env.ts:226" in prompt_user  # o achado determinístico entrou no prompt
    assert "FATOS" in prompt_user  # como fato, não opinião
