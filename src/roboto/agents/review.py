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
VALIDAR_ISSUE_SYSTEM = (
    "Você valida a PRONTIDÃO de uma issue para dev (DoR semântico): critérios de aceite "
    "verificáveis, escopo claro, sem ambiguidade. Dê também sua CONFIANÇA no julgamento. Responda "
    "EXATAMENTE:\nBEM_DEFINIDA: sim|nao\nCONFIANCA: alta|media|baixa\n"
    "LACUNAS:\n- <cada lacuna que impede o dev, se houver>"
)
REVIEW_PR_SYSTEM = (
    "Você é revisor de PR. Avalie correção, aderência ao AGENTS.md e cobertura de testes do diff.\n"
    "RUBRICA (decida o veredito por ela, não por impressão):\n"
    "- Classifique CADA problema como BLOQUEADOR ou menor.\n"
    "- BLOQUEADOR = bug de correção/segurança, requisito do AGENTS.md não cumprido, OU teste "
    "exigido ausente (inclui integração/CI quando a mudança pede).\n"
    "- VEREDITO reprovado se houver QUALQUER bloqueador. Só aprovado quando NÃO há nenhum "
    "(ressalvas menores podem existir num aprovado, mas liste-as).\n"
    "- Na dúvida entre aprovar e reprovar, REPROVE.\n"
    "Responda EXATAMENTE:\nVEREDITO: aprovado|reprovado\nPROBLEMAS:\n"
    "- <cada problema; prefixe [BLOQUEADOR] ou [menor]>"
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
class IssueReadiness:
    """Saída ESTRUTURADA do validador semântico da issue (#160): não-binária."""

    bem_definida: bool
    confianca: str  # alta | media | baixa
    lacunas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PullRequest:
    number: int
    author: str
    title: str
    diff: str


def _section_text(body: str, heading: str) -> str:
    """Texto sob a seção `## {heading}` até a próxima seção de nível IGUAL/SUPERIOR.

    Subseções mais profundas (`###`+) ficam DENTRO do texto — senão um `- [ ]` sob
    `### Teste 1` dentro de `## Critérios de aceite` seria perdido (o corte antigo quebrava
    no primeiro `###`). Vazio se a seção não existe. Match leniente do título (substring,
    case-insensitive) p/ aceitar variações como 'Critérios de aceite (TDD)'.
    """
    target = heading.strip().lower()
    out: list[str] = []
    level = 0  # nº de '#' do heading capturado; 0 = ainda não capturando
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            depth = len(stripped) - len(stripped.lstrip("#"))
            if level:
                if depth <= level:
                    break  # heading de nível igual/superior encerra a seção
                # subseção (depth > level): faz parte do texto — cai no append abaixo
            elif target in stripped.lstrip("#").strip().lower():
                level = depth
                continue
            else:
                continue
        if level:
            out.append(line)
    return "\n".join(out)


def check_issue_readiness(draft: IssueDraft) -> ReadinessVerdict:
    """Checagem estrutural do DoR (tier 1, sem LLM). ``ready`` só quando nada falta."""
    missing: list[str] = []
    if not draft.title.strip():
        missing.append("título")
    body = draft.body.lower()
    for section in _REQUIRED_SECTIONS:
        if section.lower() not in body:
            missing.append(f"seção '{section}'")
    # DoR "testável": o item verificável tem de estar SOB 'Critérios de aceite' — não basta um
    # '- [ ]' em qualquer lugar (ex.: só no DoD). Checa só se a seção existe.
    aceite = _section_text(draft.body, "Critérios de aceite")
    if "critérios de aceite" in body and "- [ ]" not in aceite:
        missing.append("critério de aceite verificável (item '- [ ]' sob 'Critérios de aceite')")
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


def _parse_readiness(text: str) -> IssueReadiness:
    """Determinístico: lê BEM_DEFINIDA / CONFIANCA / LACUNAS da saída estruturada do juiz."""
    bem = False
    conf = "media"
    lacunas: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if low.startswith("bem_definida:"):
            bem = "sim" in low
        elif low.startswith(("confianca:", "confiança:")):
            conf = next((c for c in ("alta", "baixa", "media", "média") if c in low), "media")
            conf = "media" if conf == "média" else conf
        elif line.startswith(("-", "*")):
            lacunas.append(line.lstrip("-* ").strip())
    return IssueReadiness(bem_definida=bem, confianca=conf, lacunas=lacunas)


async def validar_issue_semantica(
    draft: IssueDraft, gateway: ModelGateway
) -> Result[IssueReadiness, Error]:
    """Camadas 2+3 do validador de prontidão (#160): juiz ESTRUTURADO + ESCALADA a frontier quando
    a confiança é baixa (barato-primeiro; só paga o modelo forte na dúvida). Use APÓS a camada 1
    determinística (`check_issue_readiness`). Gerador (CHEAP) ≠ validador (JUDGE/FRONTIER)."""
    messages = [
        ChatMessage(role="system", content=VALIDAR_ISSUE_SYSTEM),
        ChatMessage(role="user", content=f"{draft.title}\n\n{draft.body}"),
    ]
    result = await gateway.complete(messages, Tier.JUDGE)
    if isinstance(result, Err):
        return Err(result.error)
    verdict = _parse_readiness(result.value.text)
    if verdict.confianca == "baixa":  # escala p/ o tier forte e usa o veredito dele
        strong = await gateway.complete(messages, Tier.FRONTIER)
        if isinstance(strong, Ok):
            verdict = _parse_readiness(strong.value.text)
    return Ok(verdict)


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
