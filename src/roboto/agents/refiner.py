"""Agente de Refinamento — primeiro agente real (D2).

Transforma uma solicitação humana (texto ou áudio transcrito) num **rascunho de issue**
(``IssueDraft``). O julgamento/geração é do modelo (via ``ModelGateway``); tudo ao redor é
determinístico e testável. A **materialização** vira issue no GitHub (fonte da verdade, D15/D20)
— feita a jusante pelo outbox quando o GitHub App existir; aqui paramos no rascunho + ack.
"""

from __future__ import annotations

from dataclasses import dataclass

from roboto.agents.breakdown import Breakdown, parse_breakdown
from roboto.channels.model import InboundMessage, MessageKind, OutboundMessage
from roboto.llm.port import ChatMessage, ModelGateway, Tier, Transcriber
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

REFINE_SYSTEM = (
    "Você é o agente de refinamento. Produza uma ISSUE COMPLETA e acionável "
    "(DoR satisfeito) — nada é codado sem uma issue assim. "
    "Responda EXATAMENTE neste formato, sem texto extra:\n"
    "TITLE: <título curto em Conventional Commits>\n"
    "BODY:\n"
    "## Contexto\n<problema / por que>\n"
    "## Escopo\n<arquivos/áreas afetados>\n"
    "## Critérios de aceite\n- [ ] <verificável>\n"
    "## DoD\n- [ ] testes (TDD) · lint/typecheck · review (reviewer≠autor) · CI verde\n"
    "## Fora de escopo\n<o que NÃO fazer>"
)


@dataclass(frozen=True)
class IssueDraft:
    title: str
    body: str


@dataclass(frozen=True)
class Refined:
    transcript: str  # texto efetivo usado (transcrição, se veio áudio)
    draft: IssueDraft
    ack: OutboundMessage


def _parse_draft(text: str) -> IssueDraft:
    """Extrai TITLE:/BODY:. Tolerante: se faltar marcador, usa a 1ª linha como título."""
    title = ""
    body_lines: list[str] = []
    in_body = False
    for line in text.splitlines():
        if line.startswith("TITLE:"):
            title = line[len("TITLE:") :].strip()
        elif line.startswith("BODY:"):
            in_body = True
            body_lines.append(line[len("BODY:") :].strip())
        elif in_body:
            body_lines.append(line)
    if not title:
        stripped = text.strip()
        title = stripped.splitlines()[0][:120] if stripped else "(sem título)"
    return IssueDraft(title=title, body="\n".join(body_lines).strip())


CONVERSE_SYSTEM = (
    "Você é um PO entrevistando para montar uma ISSUE acionável (DoR: Contexto, Escopo, "
    "Critérios de aceite verificáveis, DoD). Dada a conversa até aqui:\n"
    "- Se FALTAR informação essencial, faça UMA pergunta objetiva começando com 'PERGUNTA:'.\n"
    "- Se já dá pra montar a issue, responda SÓ a issue, sem texto extra:\n"
    "TITLE: <título curto em Conventional Commits>\n"
    "BODY:\n## Contexto\n<...>\n## Escopo\n<...>\n## Critérios de aceite\n- [ ] <verificável>\n"
    "## DoD\n- [ ] testes · lint/typecheck · review · CI\n## Fora de escopo\n<...>\n"
    "Uma pergunta por vez. Prefira PROPOR assim que tiver o suficiente — não interrogue à toa."
)


@dataclass(frozen=True)
class ConversationStep:
    """Passo da conversa de refino: ou uma pergunta ao humano, ou um rascunho pronto."""

    question: str | None  # preenchido quando falta info
    draft: IssueDraft | None  # preenchido quando já dá pra propor


async def converse(
    transcript: list[tuple[str, str]], gateway: ModelGateway
) -> Result[ConversationStep, Error]:
    """Entrevistador multi-turno: recebe o histórico e decide perguntar ou propor o rascunho."""
    messages = [ChatMessage(role="system", content=CONVERSE_SYSTEM)]
    messages.extend(ChatMessage(role=role, content=content) for role, content in transcript)
    result = await gateway.complete(messages, Tier.CHEAP)
    if isinstance(result, Err):
        return Err(result.error)
    text = result.value.text.strip()
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if first.upper().startswith("PERGUNTA:"):
        idx = text.upper().index("PERGUNTA:") + len("PERGUNTA:")
        return Ok(ConversationStep(question=text[idx:].strip() or text, draft=None))
    return Ok(ConversationStep(question=None, draft=_parse_draft(text)))


BREAKDOWN_SYSTEM = (
    "Você é o agente de refinamento DESTRINCHANDO um ÉPICO em sub-issues menores e executáveis. "
    "Dado o épico e a conversa até aqui:\n"
    "- Antes de propor, se precisar VALIDAR algo (lib/versão, viabilidade, breaking change, "
    "abordagem), PESQUISE na web e CITE a fonte (URL) no ponto correspondente.\n"
    "- Se FALTAR info essencial que não dá pra inferir do texto nem da pesquisa, faça UMA pergunta "
    "objetiva começando com 'PERGUNTA:'.\n"
    "- Quando já der pra destrinchar, responda SÓ a lista, sem texto extra, neste formato:\n"
    "ITEM: <título curto da sub-issue, imperativo>\n"
    "- <ponto a cobrir — NOMEIE o artefato/arquivo/decisão que o refino vai desenrolar>\n"
    "- <ponto a cobrir>\n"
    "DEPENDE: nenhuma | da anterior | #N   (de QUEM esta sub-issue depende; default = da anterior; "
    "use '#N' p/ apontar o item exato — forme um GRAFO, não uma fila: encadeie só dependência "
    "REAL)\n"
    "ITEM: <próxima sub-issue>\n...\n"
    "REGRAS do destrinchamento:\n"
    "- UM item = UMA responsabilidade. NÃO funda concerns distintos (ex.: prazos + ranking + "
    "prêmio num item só); separe. Um BUG/achado nomeado no épico vira item PRÓPRIO.\n"
    "- Se o épico embute DECISÃO DE ARQUITETURA (durabilidade, idempotência, concorrência, "
    "scheduler, 'se sobrepõe a #'), comece por um item de PESQUISA e um de ADR (duas visões → "
    "decisão) ANTES de schema/código; e trate garantias transversais (idempotência/exactly-once/"
    "ownership) e TESTES de durabilidade como entregáveis explícitos.\n"
    "- Se o épico tem USUÁRIO FINAL, inclua ≥1 item de UI/JORNADA (telas, estados, notificações) — "
    "não deixe a experiência só no backend; documentar o fluxo NÃO substitui construí-lo.\n"
    "- Documentação de fluxo/regras marcada como 'antes de implementar' NÃO pode ser o ÚLTIMO: "
    "posicione-a logo após o ADR.\n"
    "Cada ITEM é um ESQUELETO (título + pontos) — NÃO escreva DoR completo aqui; o refino a fundo "
    "1-a-1 depois. Quantos itens o épico exigir; não infle, mas não funda para caber num teto."
)


@dataclass(frozen=True)
class BreakdownStep:
    """Passo da conversa de breakdown: ou uma pergunta ao humano, ou o breakdown proposto."""

    question: str | None
    breakdown: Breakdown | None


async def breakdown_converse(
    transcript: list[tuple[str, str]], gateway: ModelGateway
) -> Result[BreakdownStep, Error]:
    """Destrincha um épico multi-turno: pergunta (PERGUNTA:) ou propõe os N esqueletos (ITEM:)."""
    messages = [ChatMessage(role="system", content=BREAKDOWN_SYSTEM)]
    messages.extend(ChatMessage(role=role, content=content) for role, content in transcript)
    result = await gateway.complete(messages, Tier.CHEAP)
    if isinstance(result, Err):
        return Err(result.error)
    text = result.value.text.strip()
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if first.upper().startswith("PERGUNTA:"):
        idx = text.upper().index("PERGUNTA:") + len("PERGUNTA:")
        return Ok(BreakdownStep(question=text[idx:].strip() or text, breakdown=None))
    return Ok(BreakdownStep(question=None, breakdown=parse_breakdown(text)))


async def refine(raw_text: str, gateway: ModelGateway) -> Result[IssueDraft, Error]:
    messages = [
        ChatMessage(role="system", content=REFINE_SYSTEM),
        ChatMessage(role="user", content=raw_text),
    ]
    result = await gateway.complete(messages, Tier.CHEAP)
    if isinstance(result, Err):
        return Err(result.error)
    return Ok(_parse_draft(result.value.text))


async def handle_inbound(
    msg: InboundMessage, gateway: ModelGateway, transcriber: Transcriber
) -> Result[Refined, Error]:
    """Áudio -> STT -> refino -> rascunho + ack. Determinístico dadas as portas."""
    text = msg.text
    if msg.kind is MessageKind.AUDIO:
        if msg.audio is None:
            return Err(Error("invalid", "mensagem de áudio sem bytes"))
        transcription = await transcriber.transcribe(msg.audio, msg.audio_name or "audio.ogg")
        if isinstance(transcription, Err):
            return Err(transcription.error)
        text = transcription.value
    if not text.strip():
        return Err(Error("invalid", "mensagem vazia"))
    drafted = await refine(text, gateway)
    if isinstance(drafted, Err):
        return Err(drafted.error)
    draft = drafted.value
    ack = OutboundMessage(chat_id=msg.chat_id, text=f"Rascunho pronto: {draft.title}")
    return Ok(Refined(transcript=text, draft=draft, ack=ack))
