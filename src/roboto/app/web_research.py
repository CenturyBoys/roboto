"""Pesquisa web HARNESS-DRIVEN para o refino (determinismo primeiro).

Aprendizado do PoC (2026-11-04): dar a tool de busca (MCP) ao modelo NÃO funciona com os modelos
locais — o GLM-4.5-Air confundiu o `ToolSearch` (achar tool) com a busca web e travou num loop; o
padrão se repete com code-intel. Então o HARNESS roda a busca e INJETA as fontes no prompt: o
modelo só lê e cita, nunca descobre/invoca tool. Igual à decisão do code-intel harness-driven.

Fluxo: `needs_research` (gatilho determinístico) → queries (do bloco "🔎 Pesquisa" da issue, OU um
LLM barato gera) → Tavily REST → bloco "## Fontes" markdown injetado no contexto do refino.
I/O injetável (`fetch`, `gateway`) → testável em tier-1.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from roboto.llm.decide import Decider
from roboto.llm.port import ChatMessage, ModelGateway, Tier
from roboto.result import Err

_TAVILY_URL = "https://api.tavily.com/search"

# Gatilho CONSERVADOR: pesquisa NÃO é obrigatória — só em DECISÃO que depende de validação externa
# (convenção/boas-práticas/trade-off/estado da arte) ou no marcador explícito. "pesquisar" sozinho
# NÃO dispara. Degrada gracioso: sem gatilho OU sem fonte, o refino segue normal (nunca bloqueia).
_SIGNALS = (
    "🔎",
    "best practice",
    "boas práticas",
    "melhores práticas",
    "convenção",
    "convention",
    "estado da arte",
    "state of the art",
    "padrão de mercado",
    "padrão da indústria",
    "escolher entre",
    "optar entre",
    "trade-off",
    "tradeoff",
    "benchmark",
)

# fetch: (url, payload_json) -> dict. Injetável; default usa httpx (só em runtime).
Fetch = Callable[[str, dict[str, object]], Awaitable[dict[str, object]]]
# gera queries a partir de (title, body): usado quando a issue não traz queries explícitas.
QueryGen = Callable[[str, str], Awaitable[list[str]]]


def needs_research(title: str, body: str) -> bool:
    """A issue é DECISÃO que precisa de validação externa crítica? Determinístico e CONSERVADOR
    (sem LLM): pesquisa é a exceção, não a regra. "pesquisar" genérico não dispara — só marcador 🔎
    ou vocabulário de decisão (convenção/boas-práticas/trade-off). Não-bloqueante a jusante."""
    hay = f"{title}\n{body}".lower()
    return any(sig in hay for sig in _SIGNALS)


_RESEARCH_QUESTION = (
    "Esta issue é uma decisão que precisa CRITICAMENTE de pesquisa web de fontes externas (boas "
    "práticas / estado da arte) para ser bem refinada? Trade-offs já conhecidos e critérios "
    "internos do projeto NÃO exigem pesquisa web."
)


async def research_is_critical(
    title: str, body: str, *, decider: Decider | None = None, min_confidence: float = 0.6
) -> bool:
    """Gate de pesquisa (AFROUXADO p/ permitir busca além do vocabulário fixo).

    SEM `decider`: decide pelo keyword determinístico (`needs_research`) — fallback barato.
    COM `decider` (Jev): ele julga a CRITICIDADE de QUALQUER issue — o keyword NÃO é mais pré-gate
    duro (antes descartava tudo que não batesse palavra; agora o Jev vê toda issue e decide). Só
    pesquisa se decision=True e confiança ≥ limiar. Se o Jev falhar, cai no keyword. Degrada,
    nunca bloqueia (determinismo 1º)."""
    keyword_hit = needs_research(title, body)
    if decider is None:
        return keyword_hit  # sem Jev: keyword decide (fallback)
    verdict = await decider.decide(_RESEARCH_QUESTION, f"Título: {title}\n\n{body}")
    if isinstance(verdict, Err):
        return keyword_hit  # Jev falhou → cai no keyword (não bloqueia o refino)
    return verdict.value.decision and verdict.value.confidence >= min_confidence


def extract_seed_queries(body: str) -> list[str]:
    """Queries explícitas do bloco '🔎 Pesquisa' (lista numerada) — vazio se não houver."""
    lines = body.splitlines()
    out: list[str] = []
    in_block = False
    for raw in lines:
        s = raw.strip()
        if s.startswith("#") and "🔎" in s:
            in_block = True
            continue
        if in_block:
            if s.startswith("#"):  # próxima seção encerra o bloco
                break
            m = re.match(r"^\d+\.\s+(.*)$", s)
            if m:
                q = m.group(1).strip()
                # tira ênfase/markdown básico e crases
                q = re.sub(r"[`*]", "", q).strip()
                if q:
                    out.append(q)
    return out


async def generate_queries(title: str, body: str, gateway: ModelGateway) -> list[str]:
    """Um LLM barato gera até 3 queries de busca (1 por linha), numa chamada estruturada isolada."""
    system = (
        "Você gera queries de busca web para fundamentar o refino de uma issue de engenharia. "
        "Dada a issue, devolva ATÉ 3 queries curtas em inglês ou português, UMA POR LINHA, "
        "sem numeração, sem comentário, sem texto extra."
    )
    msgs = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=f"Título: {title}\n\n{body}"),
    ]
    res = await gateway.complete(msgs, Tier.CHEAP)
    if isinstance(res, Err):
        return []
    out: list[str] = []
    for ln in res.value.text.splitlines():
        q = re.sub(r"^[\s\d.\-*•]+", "", ln).strip().strip("`")
        if q:
            out.append(q)
    return out[:3]


async def _httpx_fetch(url: str, payload: dict[str, object]) -> dict[str, object]:
    import httpx  # import tardio: só runtime precisa

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, dict) else {}


async def tavily_search(
    query: str, *, api_key: str, fetch: Fetch | None = None, max_results: int = 3
) -> list[dict[str, object]]:
    """Uma busca no Tavily REST. Erro vira lista vazia (degrada, não quebra o refino)."""
    do_fetch = fetch or _httpx_fetch
    payload: dict[str, object] = {"api_key": api_key, "query": query, "max_results": max_results}
    try:
        data = await do_fetch(_TAVILY_URL, payload)
    except Exception:  # noqa: BLE001 — rede/provedor: degrada p/ "sem fonte"
        return []
    results = data.get("results") or []
    return [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []


def _sources_block(by_query: list[tuple[str, list[dict[str, object]]]]) -> str:
    """Formata o bloco markdown '## Fontes' (vazio se nada foi encontrado)."""
    chunks: list[str] = []
    for query, results in by_query:
        if not results:
            continue
        chunks.append(f"### {query}")
        for r in results:
            url = str(r.get("url") or "").strip()
            title = str(r.get("title") or url or "fonte").strip()
            snippet = " ".join(str(r.get("content") or "").split())[:240]
            chunks.append(f"- [{title}]({url}) — {snippet}")
    if not chunks:
        return ""
    header = (
        "## Fontes (pesquisa web — USE e CITE as URLs na proposta; NÃO pesquise você mesmo)"
    )
    return header + "\n" + "\n".join(chunks)


async def research_block(
    title: str,
    body: str,
    *,
    tavily_key: str,
    gateway: ModelGateway | None = None,
    fetch: Fetch | None = None,
    query_gen: QueryGen | None = None,
    max_queries: int = 3,
) -> str:
    """Orquestra o pre-step: queries (bloco da issue OU LLM) → Tavily → bloco de fontes markdown.

    Vazio se não há chave, não há queries, ou nada foi encontrado. Puro-ish (I/O injetável).
    """
    if not tavily_key:
        return ""
    queries = extract_seed_queries(body)
    if not queries:
        if query_gen is not None:
            queries = await query_gen(title, body)
        elif gateway is not None:
            queries = await generate_queries(title, body, gateway)
    if not queries:
        return ""
    by_query: list[tuple[str, list[dict[str, object]]]] = []
    for q in queries[:max_queries]:
        results = await tavily_search(q, api_key=tavily_key, fetch=fetch)
        by_query.append((q, results))
    return _sources_block(by_query)
