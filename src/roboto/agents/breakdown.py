"""Breakdown de épico (refino): detectar épico + modelar/parsear sub-issues ESQUELETO.

Parte do CORAÇÃO do fleet (refino de issue). Determinístico onde dá: a DETECÇÃO de épico é
heurística de código — não decisão cega de LLM; o modelo só gera o conteúdo do breakdown, e o
destrinchar é confirmado na conversa. Cada sub-issue é um ESQUELETO (título + pontos + dependência
da anterior), refinada a fundo 1-a-1 depois. O encadeamento vira ``Depende de #N`` e pluga direto no
gate ``app/deps.py:blocked_by`` (issue dependente fica em WAITING até a anterior fechar).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

# --- detecção de épico (determinística) --------------------------------------------------------

# "épico"/"epico"/"epic" como PALAVRA (não "epicentro"); cobre acento e caixa.
_EPIC_WORD = re.compile(r"\b[eé]pico\b|\bepic\b", re.IGNORECASE)
# checkbox de critério/escopo: "- [ ]" ou "- [x]"
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[[ xX]\]", re.MULTILINE)
# cabeçalhos que indicam MÚLTIPLOS cenários de teste/critério (sinal de amplitude)
_SCENARIO = re.compile(
    r"^\s*#{1,6}?\s*(teste\s*\d|cen[aá]rio|crit[eé]rio)", re.IGNORECASE | re.MULTILINE
)
# menção explícita a destrinchar
_BREAKDOWN_HINT = re.compile(r"breakdown|sub-?issue|sub-?tarefa|destrinch", re.IGNORECASE)

_CHECKBOX_THRESHOLD = 8  # muitos critérios = provável amplitude de épico


def is_epic(title: str, body: str) -> bool:
    """Heurística determinística: esta issue é um ÉPICO que merece ser destrinchado?

    Sinal FORTE: "épico" como palavra no título → épico. Senão, soma sinais do corpo (palavra
    épico, muitos checkboxes, múltiplos cenários, menção a breakdown) e decide por ≥2 sinais.
    """
    if _EPIC_WORD.search(title or ""):
        return True
    body = body or ""
    sinais = 0
    if _EPIC_WORD.search(body):
        sinais += 1
    if len(_CHECKBOX.findall(body)) >= _CHECKBOX_THRESHOLD:
        sinais += 1
    if len(_SCENARIO.findall(body)) >= 3:
        sinais += 1
    if _BREAKDOWN_HINT.search(body):
        sinais += 1
    return sinais >= 2


# --- dimensões de cobertura (determinísticas) --------------------------------------------------
# O destrinchamento precisa COBRIR as dimensões que o épico implica — não depender do motor
# lembrar. Mesma filosofia da régua ``needs_research``: sinal de código decide, não o LLM.

# épico ARQUITETURAL: embute decisão de arquitetura → exige pesquisa + ADR antes de codar.
_ARCH_SIGNAL = re.compile(
    r"\badr\b|duas\s+vis[õo]es|trade-?off|dur[aá]vel|idempot|exactly-?once|\bscheduler\b|"
    r"\bworker\b|concorr[êe]ncia|dono[ -]?[úu]nico|se\s+sobrep[õo]e\s+a\s+#",
    re.IGNORECASE,
)
# épico com USUÁRIO FINAL: a jornada/UI tem de ser entregável próprio (não diluir no backend).
_UX_SIGNAL = re.compile(
    r"\btela\b|\bui\b|\bux\b|\bpwa\b|notifica|\bpush\b|jornada|usu[aá]rio|jogador|inscri[çc]|"
    r"ranking|\bcopy\b|experi[êe]ncia|interface",
    re.IGNORECASE,
)


def is_architectural(title: str, body: str) -> bool:
    """O épico embute DECISÃO DE ARQUITETURA (pesquisa + ADR + garantias antes de codar)?"""
    return bool(_ARCH_SIGNAL.search(f"{title or ''}\n{body or ''}"))


def needs_ux(title: str, body: str) -> bool:
    """O épico tem USUÁRIO FINAL (então jornada/UI precisa ser sub-issue própria)?"""
    return bool(_UX_SIGNAL.search(f"{title or ''}\n{body or ''}"))


# classificadores de ITEM (título+pontos): usados pelo gate de cobertura e pelo seeding do corpo.
_RESEARCH_ITEM = re.compile(r"pesquis|discovery|boas?\s+pr[aá]ticas|refer[êe]ncia", re.IGNORECASE)
_ADR_ITEM = re.compile(r"\badr\b|arquitetura|duas\s+vis[õo]es|decis[ãa]o\s+arq", re.IGNORECASE)
_UX_ITEM = re.compile(
    r"\bui\b|\bux\b|tela|jornada|notifica|\bpwa\b|interface|experi[êe]ncia", re.IGNORECASE
)
_DOC_ITEM = re.compile(r"document|fluxo\s+e\s+regras|ponta\s+a\s+ponta", re.IGNORECASE)
_SCHEMA_ITEM = re.compile(
    r"schema|modelo\s+de\s+dados|migra[çc]|\bfeat\(db\)|adicionar\s+campo", re.IGNORECASE
)
_DURABLE_ITEM = re.compile(
    r"scheduler|worker|dur[aá]vel|idempot|exactly-?once|\bfila\b|\bjob\b", re.IGNORECASE
)


def _item_text(item: SubIssueSkeleton) -> str:
    return item.title + "\n" + "\n".join(item.points)


def _looks_overloaded(item: SubIssueSkeleton) -> bool:
    """Um item = uma responsabilidade. Título que enumera vários entregáveis (vírgulas/`+`) ou com
    pontos demais provavelmente funde concerns distintos (ex.: prazos + ranking + prêmio)."""
    return item.title.count(",") >= 2 or " + " in item.title or len(item.points) >= 6


def review_breakdown(title: str, body: str, breakdown: Breakdown) -> list[str]:
    """Gate DETERMINÍSTICO de cobertura (não-LLM): cruza o que o épico IMPLICA com o que as
    sub-issues entregam e devolve AVISOS para o humano. Não bloqueia — informa; a decisão é do
    humano no ``/apply``. Pega justamente o que some num destrinchamento (UX, pesquisa/ADR,
    doc relegada, itens inchados)."""
    items = breakdown.items
    warnings: list[str] = []

    def _has(rx: re.Pattern[str]) -> bool:
        return any(rx.search(_item_text(it)) for it in items)

    if is_architectural(title, body):
        if not _has(_RESEARCH_ITEM):
            warnings.append(
                "Épico arquitetural SEM sub-issue de PESQUISA (boas práticas/discovery) "
                "antes de codar."
            )
        if not _has(_ADR_ITEM):
            warnings.append(
                "Épico arquitetural SEM sub-issue de ARQUITETURA/ADR (ex.: duas visões → decisão)."
            )
    if needs_ux(title, body) and not _has(_UX_ITEM):
        warnings.append(
            "Épico com usuário final SEM sub-issue de UI/JORNADA — a experiência não pode "
            "diluir no backend."
        )
    if items and _DOC_ITEM.search(_item_text(items[-1])):
        warnings.append(
            "Documentação de fluxo/regras é o ÚLTIMO item — se o épico pede 'documentar antes de "
            "implementar', promova-a para logo após o ADR."
        )
    for it in items:
        if _looks_overloaded(it):
            warnings.append(
                f"Sub-issue possivelmente INCHADA (vários propósitos): “{it.title}”. "
                "Separe concerns."
            )
    return warnings


# --- modelo do esqueleto -----------------------------------------------------------------------


@dataclass(frozen=True)
class SubIssueSkeleton:
    """Uma sub-issue LEVE do breakdown: título + pontos a cobrir + de quem depende.

    Dependência em DOIS níveis (compat + DAG): ``depends_on_prev`` é o encadeamento simples (só o
    1º item é False); ``depends_on_index`` é a dependência NOMEADA — o índice 0-based de um item
    que PRECEDE este. Quando preenchido, vence o encadeamento simples e forma um DAG raso (em vez de
    uma fila), para não serializar trabalho paralelizável nem empurrar transversais pro fim.
    """

    title: str
    points: list[str]
    depends_on_prev: bool  # encadeamento simples: só o 1º item é False
    depends_on_index: int | None = None  # DAG: índice 0-based do item do qual depende (precede-o)


@dataclass(frozen=True)
class Breakdown:
    items: list[SubIssueSkeleton]


# formato que o motor emite (parseável, sem texto solto):
#   ITEM: <título>
#   - <ponto>
#   - <ponto>
#   DEPENDE: nenhuma | da anterior | #N   (opcional; default = depende do item anterior)
#   ITEM: <próximo>
_ITEM = re.compile(r"^\s*ITEM:\s*(.+?)\s*$", re.IGNORECASE)
_POINT = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_DEPENDE = re.compile(r"^\s*DEPENDE:\s*(.+?)\s*$", re.IGNORECASE)
_NENHUMA = re.compile(r"nenhuma|none|nada|independente", re.IGNORECASE)
_DEP_NUM = re.compile(r"#?\s*(\d+)")  # "DEPENDE: #2" / "do item 2" -> índice nomeado (1-based)


def parse_breakdown(text: str) -> Breakdown:
    """Extrai os ITEM:/pontos. Resolve a dependência de cada item:
    - ``DEPENDE: nenhuma`` → independente;
    - ``DEPENDE: #N`` (ou "item N") → dependência NOMEADA do N-ésimo item (1-based), formando DAG;
    - ausente / "da anterior" → encadeia no item anterior (default conservador).
    Índice nomeado que não aponta para um item ANTERIOR válido é ignorado (cai no default).
    Tolerante a ruído entre itens."""
    items: list[SubIssueSkeleton] = []
    cur_title: str | None = None
    cur_points: list[str] = []
    cur_independent = False
    cur_dep_index: int | None = None

    def flush() -> None:
        nonlocal cur_title, cur_points, cur_independent, cur_dep_index
        if cur_title is not None:
            pos = len(items)  # índice 0-based deste item
            valid = cur_dep_index is not None and 0 <= cur_dep_index < pos
            named = cur_dep_index if valid else None
            if named is not None:
                depends_prev = named == pos - 1
                items.append(SubIssueSkeleton(cur_title, cur_points, depends_prev, named))
            else:
                depends_prev = pos > 0 and not cur_independent
                items.append(SubIssueSkeleton(cur_title, cur_points, depends_prev, None))
        cur_title, cur_points, cur_independent, cur_dep_index = None, [], False, None

    for line in (text or "").splitlines():
        m_item = _ITEM.match(line)
        if m_item:
            flush()
            cur_title = m_item.group(1)
            continue
        if cur_title is None:
            continue
        m_dep = _DEPENDE.match(line)
        if m_dep:
            val = m_dep.group(1)
            if _NENHUMA.search(val):
                cur_independent, cur_dep_index = True, None
            else:
                m_num = _DEP_NUM.search(val)
                cur_dep_index = int(m_num.group(1)) - 1 if m_num else None
            continue
        m_pt = _POINT.match(line)
        if m_pt:
            cur_points.append(m_pt.group(1))
    flush()
    return Breakdown(items=items)


_RESEARCH_HEADER = "## 🔎 Pesquisa (fazer ANTES de propor — use a busca web; CITE as URLs)"
_RESEARCH_VERB = re.compile(
    r"^(pesquisar|investigar|levantar|escolher\s+entre|comparar|avaliar)\s+", re.IGNORECASE
)

# blocos-semente auto-injetados por DIMENSÃO da sub-issue (espelham o bloco de pesquisa): tornam a
# cobertura ESTRUTURAL, não dependente do motor lembrar. O refino a fundo desenrola cada checkbox.
_UX_SEED = (
    "## 🎭 Jornada & UI (cobrir a experiência vivida, não só a lógica)\n"
    "- [ ] Telas/estados de cada passo (espera, ação, resultado, avanço/saída, encerramento)\n"
    "- [ ] Notificações: catálogo de eventos + copy + deep-link + tela-destino + permissão\n"
    "- [ ] Transparência de regra ao usuário (por que este resultado/estado)"
)
_SCHEMA_SEED = (
    "## 🗄️ Migração (obrigatório p/ mudança de schema)\n"
    "- [ ] Migração reversível\n"
    "- [ ] Backfill dos registros legados\n"
    "- [ ] Defaults para linhas existentes"
)
_GUARANTEES_SEED = (
    "## 🔒 Garantias transversais (durabilidade)\n"
    "- [ ] Idempotência / exactly-once nas transições (chave por ação; compare-and-set no estado)\n"
    "- [ ] Ownership/lock da região crítica\n"
    "- [ ] Teste de crash/restart/replay"
)


def _research_seed_queries(points: list[str], is_research: Callable[[str, str], bool]) -> list[str]:
    """Pontos que sinalizam pesquisa viram queries-semente (tira o verbo de comando)."""
    out: list[str] = []
    for p in points:
        if is_research("", p):
            out.append(_RESEARCH_VERB.sub("", p).strip() or p)
    return out


def skeleton_body(item: SubIssueSkeleton, dep_number: int | None) -> str:
    """Corpo da sub-issue ESQUELETO. ``dep_number`` é o NÚMERO real da issue da qual esta depende
    (já resolvido pelo materializador, seja encadeamento simples ou DAG); se dado, vira
    ``Depende de #N`` e casa com o gate (app/deps.py), segurando a issue em WAITING até a anterior
    fechar. Marca que ainda falta refino 1-a-1 (DoR).

    Pesquisa NÃO é obrigatória: só semeia o bloco ``🔎 Pesquisa`` quando a sub-issue é de DECISÃO
    que depende de validação externa (mesma régua conservadora de
    ``app/web_research.needs_research`` — convenção/boas-práticas/trade-off, não todo "pesquisar").
    Além dela, blocos por DIMENSÃO da sub-issue são auto-injetados (UX/jornada, migração de schema,
    garantias de durabilidade) — a cobertura vira estrutural, não dependente do motor lembrar.
    Import lazy p/ evitar o ciclo agents↔app (app/__init__ importa agents).
    """
    from roboto.app.web_research import needs_research

    parts = ["## Pontos a cobrir"]
    if item.points:
        parts.extend(f"- {p}" for p in item.points)
    else:
        parts.append("- (a detalhar)")
    if needs_research(item.title, "\n".join(item.points)):
        block = [_RESEARCH_HEADER]
        for i, q in enumerate(_research_seed_queries(item.points, needs_research), 1):
            block.append(f"{i}. {q}")
        parts.append("\n" + "\n".join(block))
    text = _item_text(item)
    if _UX_ITEM.search(text):
        parts.append("\n" + _UX_SEED)
    if _SCHEMA_ITEM.search(text):
        parts.append("\n" + _SCHEMA_SEED)
    if _DURABLE_ITEM.search(text):
        parts.append("\n" + _GUARANTEES_SEED)
    if dep_number is not None:
        parts.append(f"\nDepende de #{dep_number}")
    parts.append("\n> Esqueleto do breakdown — refinar a fundo (DoR) antes de implementar.")
    return "\n".join(parts)
