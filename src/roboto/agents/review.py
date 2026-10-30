"""Review (D28, trilhas A/D) — em dois pontos: a ISSUE (antes do dev) e o PR (reviewer≠autor).

Escada: (1) gate estrutural da issue (tier 1, sem LLM: `check_issue_readiness`); (2) juiz
semântico da issue (`review_issue_semantics`, tier judge); (3) review de PR (`review_pr`) com
**reviewer ≠ autor**. Veredito com parsing determinístico; output do modelo é proposta (H).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from roboto.agents.refiner import IssueDraft
from roboto.llm.port import ChatMessage, ModelGateway, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

_REQUIRED_SECTIONS = ("Contexto", "Escopo", "Critérios de aceite", "DoD")

REVIEW_ISSUE_SYSTEM = (
    "Você é revisor de issues. Avalie se a issue é ACIONÁVEL: critérios de aceite verificáveis, "
    "escopo claro, DoD significativo, sem ambiguidade. Responda EXATAMENTE:\n"
    "VEREDITO: aprovado|reprovado\nPROBLEMAS:\n- <cada problema, se houver>"
)
REVIEW_PR_SYSTEM = (
    "Você é revisor de PR. Avalie correção, aderência ao AGENTS.md e cobertura de testes do diff. "
    "Responda EXATAMENTE:\nVEREDITO: aprovado|reprovado\nPROBLEMAS:\n- <cada problema, se houver>"
)


@dataclass(frozen=True)
class ReadinessVerdict:
    ready: bool
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewVerdict:
    approved: bool
    issues: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class PullRequest:
    number: int
    author: str
    title: str
    diff: str


def check_issue_readiness(draft: IssueDraft) -> ReadinessVerdict:
    """Checagem estrutural do DoR (tier 1, sem LLM). ``ready`` só quando nada falta."""
    missing: list[str] = []
    if not draft.title.strip():
        missing.append("título")
    body = draft.body.lower()
    for section in _REQUIRED_SECTIONS:
        if section.lower() not in body:
            missing.append(f"seção '{section}'")
    if "- [ ]" not in draft.body:
        missing.append("critério de aceite (nenhum item '- [ ]')")
    return ReadinessVerdict(ready=not missing, missing=missing)


def _parse_verdict(text: str) -> ReviewVerdict:
    """Determinístico: aprovado só com 'aprovado' explícito e sem 'reprovado' (conservador, H)."""
    low = text.lower()
    approved = "aprovado" in low and "reprovado" not in low
    issues = [
        line.lstrip("-* ").strip()
        for line in text.splitlines()
        if line.strip().startswith(("-", "*"))
    ]
    return ReviewVerdict(approved=approved, issues=issues, summary=text.strip()[:200])


async def review_issue_semantics(
    draft: IssueDraft, gateway: ModelGateway
) -> Result[ReviewVerdict, Error]:
    """Camada semântica do gate da issue (juiz barato). Use APÓS `check_issue_readiness`."""
    messages = [
        ChatMessage(role="system", content=REVIEW_ISSUE_SYSTEM),
        ChatMessage(role="user", content=f"{draft.title}\n\n{draft.body}"),
    ]
    result = await gateway.complete(messages, Tier.JUDGE)
    if isinstance(result, Err):
        return Err(result.error)
    return Ok(_parse_verdict(result.value.text))


async def review_pr(
    pr: PullRequest, gateway: ModelGateway, *, reviewer: str,
    verify_findings: list[str] | None = None,
) -> Result[ReviewVerdict, Error]:
    """Review de PR com reviewer ≠ autor (D): mesmo autor/revisor = bloqueado, sem LLM.

    `verify_findings`: erros de tipo achados pelo verify determinístico (code-intel/tsgo). Entram no
    prompt como FATOS (não opinião) p/ o revisor não aprovar por cima deles (ideia 1).
    """
    if reviewer == pr.author:
        return Ok(
            ReviewVerdict(
                approved=False,
                issues=["reviewer == autor: revisão exige um par diferente (trilha D)"],
                summary="bloqueado: reviewer=autor",
            )
        )
    bloco_verify = ""
    if verify_findings:
        itens = "\n".join(f"- {e}" for e in verify_findings[:30])
        bloco_verify = (
            "\n\n## Verify (code-intel/tsgo) — POSSÍVEIS erros de tipo (pode haver falso positivo "
            "de contexto):\n"
            "AVALIE cada um contra o diff: se for real, NÃO aprove sem tratar; se for falso "
            f"positivo (ex.: global do Node mal-resolvido), diga isso no parecer:\n{itens}\n"
        )
    content = f"PR #{pr.number} (autor={pr.author}): {pr.title}\n\n{pr.diff}{bloco_verify}"
    messages = [
        ChatMessage(role="system", content=REVIEW_PR_SYSTEM),
        ChatMessage(role="user", content=content),
    ]
    result = await gateway.complete(messages, Tier.JUDGE)
    if isinstance(result, Err):
        return Err(result.error)
    return Ok(_parse_verdict(result.value.text))
