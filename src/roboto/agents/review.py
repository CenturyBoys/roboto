"""Review (D28, trilhas A/D) — em dois pontos: a ISSUE (antes do dev) e o PR (reviewer≠autor).

Escada: (1) gate estrutural da issue (tier 1, sem LLM: `check_issue_readiness`); (2) juiz
semântico da issue (`review_issue_semantics`, tier judge); (3) review de PR (`review_pr`) com
**reviewer ≠ autor**. Veredito com parsing determinístico; output do modelo é proposta (H).
"""

from __future__ import annotations

import asyncio
import re
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
class SizeVerdict:
    oversized: bool  # parece ÉPICO (não cabe em 1 PR) → quebrar em sub-issues
    criterios: int = 0
    reason: str = ""


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


# acima disto a issue cheira a ÉPICO: muitos critérios = muitos entregáveis = não cabe em 1 PR.
# Conservador e TUNÁVEL. Raiz dos runaways do coder: refino que cria tarefa grande demais (#239).
_MAX_ACEITE = 7


def check_issue_size(draft: IssueDraft, *, single_deliverable: bool = False) -> SizeVerdict:
    """Right-sizing (tier 1, sem LLM): a issue cabe em 1 PR ou é um épico? Heurística determinística
    pelo nº de Critérios de aceite (proxy de entregáveis). Oversized → quebrar em sub-issues (#239).
    Conservador: só dispara BEM acima do normal (issue focada tem ~3–6 critérios).

    ``single_deliverable``: task de UM entregável (spike/definição — ver ``task_class``) NUNCA é
    épico por critérios; seu done é um único artefato e um checklist minucioso não a torna multi-PR.
    O chamador classifica o tipo (determinístico) e passa aqui."""
    aceite = _section_text(draft.body, "Critérios de aceite")
    n = aceite.count("- [ ]")
    if single_deliverable:
        return SizeVerdict(oversized=False, criterios=n)
    if n > _MAX_ACEITE:
        return SizeVerdict(
            oversized=True,
            criterios=n,
            reason=f"{n} critérios de aceite (> {_MAX_ACEITE}) — épico, quebre em sub-issues",
        )
    return SizeVerdict(oversized=False, criterios=n)


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


# ---- Review ESTRUTURADO por finding (Trilha D) ----
# Estratégia plugável: "single" (juiz único, bem-feito, default) hoje; "multi" (multi-dimensão +
# verificação) é um hook pra ligar depois sem mexer nos chamadores (ROBOTO_REVIEW_STRATEGY).

REVIEW_PR_STRUCT_SYSTEM = (
    "You are the PR reviewer — the senior dev who gets paged when this breaks. Focus on LOGIC and "
    "DESIGN — do NOT reflag lint/type/test/build/secret (CI already catches those; it's waste). "
    "Reviewer ≠ author.\n"
    "ORDER OF IMPORTANCE (decide by it, not by impression): correct > safe > holds under load > "
    "tested > fast > lean.\n"
    "GOLDEN RULE — NO CASE, NO FINDING: every finding needs a CONCRETE CASE (this input/situation "
    "→ this wrong result). Before emitting, RE-READ the lines and confirm the case is REAL (the "
    "caller exists, the value can really be empty, the code really is used). When unsure, do NOT "
    "emit. NO style taste, no 'consider', no 'maybe', no vague worry.\n"
    "A shortcut marked with a `shortcut: <limit>` (or `ponytail:`) comment is a DECISION, not a "
    "finding — unless the expected load already crosses the named limit.\n"
    "Propose the SMALLEST fix; prefer ones that DELETE code; never add a layer/framework/config "
    "the problem does not need.\n"
    "For EACH real problem, emit a block EXACTLY in this format — keep the field keys and the "
    "severity values as shown (Portuguese); write the text values in PORTUGUESE:\n"
    "FINDING\n"
    "severidade: bloqueador|menor\n"
    "arquivo: <path ou ->\n"
    "linha: <número ou 0>\n"
    "confianca: alta|media|baixa\n"
    "titulo: <frase curta em PT>\n"
    "evidencia: <the concrete CASE in 1-2 lines (em PT): 'entrada/situação X → resultado errado "
    "Y'; quote only the MINIMAL snippet, never paste the file>\n"
    "recomendacao: <MANDATORY, em PT — the CONCRETE step to fix, imperative (ex.: 'remova o bloco "
    "it(...) duplicado'); never empty nor generic>\n"
    "END\n"
    "No real problem = emit NO block. Any untreated `bloqueador` fails the PR.\n"
    "Every finding NEEDS an actionable `recomendacao` — a weak model fixes it and only acts on the "
    "'how to fix'; a finding without a recommendation is useless."
)


@dataclass(frozen=True)
class Finding:
    titulo: str
    severidade: str  # bloqueador | menor
    arquivo: str
    linha: int  # 0 = sem linha específica
    confianca: str  # alta | media | baixa
    evidencia: str = ""
    recomendacao: str = ""


def _parse_findings(text: str) -> list[Finding]:
    """Determinístico: extrai os blocos FINDING…END da saída do juiz."""
    out: list[Finding] = []
    for bloco in re.findall(r"FINDING\s*(.*?)\s*END", text, re.DOTALL | re.IGNORECASE):
        campos: dict[str, str] = {}
        for line in bloco.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                campos[k.strip().lower()] = v.strip()
        titulo = campos.get("titulo", "").strip()
        if not titulo:
            continue
        sev = "bloqueador" if "bloq" in campos.get("severidade", "").lower() else "menor"
        low_conf = campos.get("confianca", "").lower()
        conf = next((c for c in ("alta", "baixa", "media", "média") if c in low_conf), "media")
        try:
            linha = int(campos.get("linha", "0") or 0)
        except ValueError:
            linha = 0
        evidencia = campos.get("evidencia", "").strip()
        # #2: reviewer fraco às vezes deixa `recomendacao` vazia → o impl recebe o "o quê" sem o
        # "como" e não conserta. Garante no código: evidência concreta > derivar do título.
        recomendacao = campos.get("recomendacao", "").strip() or evidencia or f"Corrigir: {titulo}"
        out.append(
            Finding(
                titulo=titulo,
                severidade=sev,
                arquivo=campos.get("arquivo", "-").strip() or "-",
                linha=linha,
                confianca="media" if conf == "média" else conf,
                evidencia=evidencia,
                recomendacao=recomendacao,
            )
        )
    return out


def aprovado_por_findings(findings: list[Finding]) -> bool:
    """Veredito determinístico: aprovado só se NÃO há bloqueador."""
    return not any(f.severidade == "bloqueador" for f in findings)


async def review_pr_findings(
    pr: PullRequest, gateway: ModelGateway, *, reviewer: str,
    verify_findings: list[str] | None = None, contexto_previo: list[str] | None = None,
    lente: str = "",
) -> Result[list[Finding], Error]:
    """Review ESTRUTURADO (estratégia 'single'): findings tipados. reviewer==autor bloqueia.

    `lente` (P1b): foco extra acoplado ao system — a estratégia 'multi' roda VÁRIAS lentes em
    paralelo (cada uma caça uma classe de defeito) pra achar tudo numa passada, sem whack-a-mole.

    `contexto_previo` (#151): reviews/comentários anteriores do PR — o juiz verifica CADA ponto
    contra o diff atual: resolvido → não repete; não resolvido → MANTÉM (bloqueador segue
    bloqueando). Nunca aprova só porque algo 'já foi apontado' (bug pego no ponta-a-ponta: o
    re-review aprovava um PR com bloqueadores abertos só por já terem sido comentados)."""
    if reviewer == pr.author:
        bloq = Finding(
            "revisão exige um par diferente (reviewer≠autor)", "bloqueador", "-", 0, "alta"
        )
        return Ok([bloq])
    bloco_verify = ""
    if verify_findings:
        itens = "\n".join(f"- {e}" for e in verify_findings[:30])
        bloco_verify = (
            "\n\n## Verify (code-intel/tsgo) — POSSÍVEIS erros de tipo (avalie contra o diff; se "
            f"real, vire finding; se falso positivo, ignore):\n{itens}\n"
        )
    bloco_previo = ""
    if contexto_previo:
        anteriores = "\n---\n".join(c.strip() for c in contexto_previo[:5])
        bloco_previo = (
            "\n\n## Reviews ANTERIORES deste PR — verifique CADA ponto contra o diff ATUAL: se foi "
            "RESOLVIDO no código, NÃO repita; se continua NÃO resolvido, MANTENHA como finding (um "
            "bloqueador não resolvido SEGUE bloqueando). NÃO aprove só porque algo já foi apontado "
            f"— só aprove se os pontos foram de fato corrigidos:\n{anteriores}\n"
        )
    content = (
        f"PR #{pr.number} (autor={pr.author}): {pr.title}\n\n{pr.diff}{bloco_verify}{bloco_previo}"
    )
    system = REVIEW_PR_STRUCT_SYSTEM + (f"\n\nLENTE (foque SÓ nisto): {lente}" if lente else "")
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=content),
    ]
    result = await gateway.complete(messages, Tier.JUDGE)
    if isinstance(result, Err):
        return Err(result.error)
    return Ok(_parse_findings(result.value.text))


# P1b: lentes do review 'multi' — cada uma caça UMA classe de defeito; rodam em PARALELO e a UNIÃO
# dos achados sai numa passada só (vs. o whack-a-mole do run-1047, que achou 1 bloqueador por rodada
# no MESMO bug de idempotência em 4 sites). São as classes que mais escapam ao juiz único.
_LENSES: tuple[str, ...] = (
    "IDEMPOTÊNCIA/CONCORRÊNCIA: efeito exatamente-uma-vez sob retry/crash? a chave de dedup é "
    "gravada só APÓS o efeito durável (nunca antes)? replay devolve o MESMO estado aplicado? "
    "CAS/lock/owner-token corretos? corrida entre entregas concorrentes?",
    "DADOS/PERSISTÊNCIA: campo/coluna que não existe no schema/cliente? migration ausente? no-op "
    "silencioso disfarçado de sucesso? escrita parcial fora de transação? o efeito durável "
    "acontece de fato (não só em memória/mock)?",
    "ERRO/RETRY/RESILIÊNCIA: erro transitório sem retry? job vai pra failed sem reentrega? exceção "
    "engolida? timeout/caminho de falha não coberto? ordem efeito-vs-commit sob falha no meio?",
    "CONTRATO×TESTE: o teste cobre o comportamento NOVO (não só o caminho feliz)? o mock reflete a "
    "PRODUÇÃO (não um atalho que faz o teste passar por acidente)? bordas (vazio, N<2, limite) "
    "cobertas? alguma asserção passa por coincidência?",
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """União determinística: colapsa findings iguais (mesmo arquivo:linha + título ~igual) que
    lentes distintas acham em paralelo. Em empate, BLOQUEADOR vence o menor (sem rebaixar)."""
    best: dict[tuple[str, int, str], Finding] = {}
    ordem: list[tuple[str, int, str]] = []
    for f in findings:
        key = (f.arquivo.strip().lower(), f.linha, _norm(f.titulo)[:60])
        atual = best.get(key)
        if atual is None:
            best[key] = f
            ordem.append(key)
        elif f.severidade == "bloqueador" and atual.severidade != "bloqueador":
            best[key] = f  # mantém a posição; promove a severidade
    return [best[k] for k in ordem]


def _added_lines(diff: str) -> list[tuple[str, int, str]]:
    """Parse enxuto de unified diff → (arquivo, nº da linha NOVA, texto) por linha ADICIONADA."""
    out: list[tuple[str, int, str]] = []
    arquivo = ""
    novo = 0
    for line in (diff or "").splitlines():
        if line.startswith("+++ b/"):
            arquivo = line[6:].strip()
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            novo = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((arquivo, novo, line[1:]))
            novo += 1
        elif not line.startswith("-"):
            novo += 1
    return out


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def sweep_sibling_sites(diff: str, findings: list[Finding], *, max_extra: int = 6) -> list[Finding]:
    """Varredura DETERMINÍSTICA de invariante (P1b): quando uma lente aponta um BLOQUEADOR numa
    linha, procura o MESMO identificador-chave em OUTRAS linhas adicionadas do mesmo arquivo e marca
    cada site ainda não coberto. É o que falta no whack-a-mole: achado o site 1, varrer 2/3/4 de uma
    vez (determinismo, não 'lembrar' do LLM). Conservador: emite só `menor` ('mesmo padrão'),
    nunca bloqueador novo, e limitado por `max_extra`."""
    adicionadas = _added_lines(diff)
    por_arquivo: dict[str, list[tuple[int, str]]] = {}
    for arq, ln, txt in adicionadas:
        por_arquivo.setdefault(arq, []).append((ln, txt))
    cobertas = {(f.arquivo.strip(), f.linha) for f in findings}
    extras: list[Finding] = []
    for f in findings:
        if f.severidade != "bloqueador" or f.linha <= 0 or f.arquivo in ("", "-"):
            continue
        linha_txt = next(
            (t for ln, t in por_arquivo.get(f.arquivo, []) if ln == f.linha), ""
        )
        idents = {i for i in _IDENT.findall(linha_txt) if not i.isdigit()}
        for ln, txt in por_arquivo.get(f.arquivo, []):
            if (f.arquivo, ln) in cobertas or ln == f.linha:
                continue
            if any(i in txt for i in idents):
                extras.append(Finding(
                    titulo=f"Mesmo padrão de '{f.titulo}' aqui — verifique",
                    severidade="menor", arquivo=f.arquivo, linha=ln, confianca="media",
                    evidencia=txt.strip()[:160],
                    recomendacao=f"Aplicar a mesma correção de '{f.titulo}' neste site.",
                ))
                cobertas.add((f.arquivo, ln))
                if len(extras) >= max_extra:
                    return extras
    return extras


async def review_pr_multi(
    pr: PullRequest, gateway: ModelGateway, *, reviewer: str,
    verify_findings: list[str] | None = None, contexto_previo: list[str] | None = None,
) -> Result[list[Finding], Error]:
    """Estratégia 'multi' (P1b): roda as lentes em PARALELO + varredura de invariante. União
    deduplicada dos achados numa passada só. Erra só se TODAS as lentes errarem."""
    if reviewer == pr.author:
        return Ok([Finding("revisão exige par diferente (reviewer≠autor)", "bloqueador", "-", 0,
                           "alta")])
    results = await asyncio.gather(*[
        review_pr_findings(
            pr, gateway, reviewer=reviewer, verify_findings=verify_findings,
            contexto_previo=contexto_previo, lente=lente,
        )
        for lente in _LENSES
    ])
    oks = [r.value for r in results if isinstance(r, Ok)]
    if not oks:  # todas as lentes erraram → propaga o 1º erro
        return results[0]
    todos = [f for sub in oks for f in sub]
    todos += sweep_sibling_sites(pr.diff, todos)
    return Ok(dedupe_findings(todos))


def formatar_finding(f: Finding) -> str:
    """Comentário INLINE enxuto e legível (regra do dono): título + recomendação à vista; a
    evidência (trecho) vai COLAPSADA em <details> — nada de parede de código no GitHub."""
    emoji = "🛑" if f.severidade == "bloqueador" else "🔸"
    corpo = f"{emoji} **[{f.severidade}]** {f.titulo} · _confiança {f.confianca}_"
    if f.recomendacao:
        corpo += f"\n\n{f.recomendacao}"
    if f.evidencia:
        det = f"<details><summary>evidência</summary>\n\n```\n{f.evidencia}\n```\n\n</details>"
        corpo += f"\n\n{det}"
    return corpo


def resumo_review(findings: list[Finding]) -> str:
    """Comentário-resumo curto (lista escaneável; detalhe fica nos inline)."""
    if not findings:
        return "✅ Review do fleet: sem apontamentos de lógica/design. Merge = gate humano."
    blk = [f for f in findings if f.severidade == "bloqueador"]
    cab = (
        f"{'🔁' if blk else '✅'} Review do fleet — {len(blk)} bloqueador(es), "
        f"{len(findings) - len(blk)} menor(es):"
    )
    linhas = [
        f"- {'🛑' if f.severidade == 'bloqueador' else '🔸'} {f.titulo}"
        f" (`{f.arquivo}`{':' + str(f.linha) if f.linha else ''})"
        for f in findings
    ]
    return cab + "\n" + "\n".join(linhas) + "\n\n_(parecer do fleet, reviewer≠autor)_"


def montar_review(findings: list[Finding]) -> tuple[list[tuple[str, int, str]], str, bool]:
    """Separa os findings em comentários INLINE (com arquivo+linha) e o corpo-resumo; devolve
    (inline, body, aprovado). Finding sem localização entra no corpo (não some)."""
    inline: list[tuple[str, int, str]] = []
    sem_loc: list[Finding] = []
    for f in findings:
        if f.arquivo and f.arquivo != "-" and f.linha > 0:
            inline.append((f.arquivo, f.linha, formatar_finding(f)))
        else:
            sem_loc.append(f)
    body = resumo_review(findings)
    if sem_loc:
        corpos = "\n\n".join(formatar_finding(f) for f in sem_loc)
        body += f"\n\n**Sem linha específica:**\n\n{corpos}"
    return inline, body, aprovado_por_findings(findings)


async def revisar_pr(
    pr: PullRequest, gateway: ModelGateway, *, reviewer: str,
    verify_findings: list[str] | None = None, contexto_previo: list[str] | None = None,
    strategy: str = "single",
) -> Result[list[Finding], Error]:
    """Dispatcher de ESTRATÉGIA de review (plugável, ROBOTO_REVIEW_STRATEGY). 'single' = juiz único
    estruturado; 'multi' (P1b) = lentes em paralelo + varredura de invariante (acha tudo numa
    passada). Qualquer outro valor cai no 'single' (conservador)."""
    if strategy == "multi":
        return await review_pr_multi(
            pr, gateway, reviewer=reviewer,
            verify_findings=verify_findings, contexto_previo=contexto_previo,
        )
    return await review_pr_findings(
        pr, gateway, reviewer=reviewer,
        verify_findings=verify_findings, contexto_previo=contexto_previo,
    )
