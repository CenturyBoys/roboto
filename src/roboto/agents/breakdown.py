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


# --- modelo do esqueleto -----------------------------------------------------------------------


@dataclass(frozen=True)
class SubIssueSkeleton:
    """Uma sub-issue LEVE do breakdown: título + pontos a cobrir + se depende da anterior."""

    title: str
    points: list[str]
    depends_on_prev: bool  # encadeamento: só o 1º item é False


@dataclass(frozen=True)
class Breakdown:
    items: list[SubIssueSkeleton]


# formato que o motor emite (parseável, sem texto solto):
#   ITEM: <título>
#   - <ponto>
#   - <ponto>
#   DEPENDE: nenhuma        (opcional; default = depende do item anterior)
#   ITEM: <próximo>
_ITEM = re.compile(r"^\s*ITEM:\s*(.+?)\s*$", re.IGNORECASE)
_POINT = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_DEPENDE = re.compile(r"^\s*DEPENDE:\s*(.+?)\s*$", re.IGNORECASE)
_NENHUMA = re.compile(r"nenhuma|none|nada|independente", re.IGNORECASE)


def parse_breakdown(text: str) -> Breakdown:
    """Extrai os ITEM:/pontos. Encadeia sequencialmente (cada um depende do anterior), salvo
    ``DEPENDE: nenhuma`` num item, que o torna independente. Tolerante a ruído entre itens."""
    items: list[SubIssueSkeleton] = []
    cur_title: str | None = None
    cur_points: list[str] = []
    cur_independent = False

    def flush() -> None:
        nonlocal cur_title, cur_points, cur_independent
        if cur_title is not None:
            depends = len(items) > 0 and not cur_independent
            items.append(SubIssueSkeleton(cur_title, cur_points, depends))
        cur_title, cur_points, cur_independent = None, [], False

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
            cur_independent = bool(_NENHUMA.search(m_dep.group(1)))
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


def _research_seed_queries(points: list[str], is_research: Callable[[str, str], bool]) -> list[str]:
    """Pontos que sinalizam pesquisa viram queries-semente (tira o verbo de comando)."""
    out: list[str] = []
    for p in points:
        if is_research("", p):
            out.append(_RESEARCH_VERB.sub("", p).strip() or p)
    return out


def skeleton_body(item: SubIssueSkeleton, prev_number: int | None) -> str:
    """Corpo da sub-issue ESQUELETO. ``Depende de #N`` casa com o gate (app/deps.py) e segura a
    issue em WAITING até a anterior fechar. Marca que ainda falta refino 1-a-1 (DoR).

    Pesquisa NÃO é obrigatória: só semeia o bloco ``🔎 Pesquisa`` quando a sub-issue é de DECISÃO
    que depende de validação externa (mesma régua conservadora de
    ``app/web_research.needs_research`` — convenção/boas-práticas/trade-off, não todo "pesquisar").
    Aí o refino harness-driven dispara a busca e usa as queries-semente (senão um LLM gera).
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
    if item.depends_on_prev and prev_number is not None:
        parts.append(f"\nDepende de #{prev_number}")
    parts.append("\n> Esqueleto do breakdown — refinar a fundo (DoR) antes de implementar.")
    return "\n".join(parts)
