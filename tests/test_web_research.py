"""Pesquisa web harness-driven do refino: gatilho, queries, Tavily (fetch injetado), fontes."""

from __future__ import annotations

from roboto.app.web_research import (
    extract_seed_queries,
    needs_research,
    research_block,
    research_is_critical,
    tavily_search,
)
from roboto.llm.decide import Decision
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class _StubDecider:
    """Decider de teste: devolve uma Decision fixa (ou Err) sem rede."""

    def __init__(self, result: Result[Decision, Error]) -> None:
        self._result = result

    async def decide(self, question: str, context: str) -> Result[Decision, Error]:
        return self._result

_BODY_COM_BLOCO = """## Pontos a cobrir
- algo

## 🔎 Pesquisa (fazer ANTES de propor — use a busca web / Tavily)
1. REST API versioning best practices — path prefix vs header
2. URL path `/v1` vs `Accept`-header versioning — trade-offs
3. API deprecation policy e `Sunset` header

## Critérios
- [ ] x
"""


def test_needs_research_por_marcador_e_palavra() -> None:
    assert needs_research("Definir convenção de versão", "qualquer corpo")
    assert needs_research("T", "precisamos pesquisar boas práticas")
    assert needs_research("T", _BODY_COM_BLOCO)  # tem o 🔎


def test_needs_research_falso_quando_nao_sinaliza() -> None:
    assert not needs_research("Corrigir bug no parser", "ajustar o split da string")


def test_needs_research_conservador_ignora_pesquisar_generico() -> None:
    # política: pesquisa NÃO é obrigatória — "pesquisar" genérico (sem decisão) não dispara
    assert not needs_research("Refatorar módulo X", "pesquisar os usos de foo no código")
    assert not needs_research("Implementar endpoint", "criar rota e retornar JSON")


def test_extract_seed_queries_pega_a_lista_numerada() -> None:
    qs = extract_seed_queries(_BODY_COM_BLOCO)
    assert len(qs) == 3
    assert qs[0] == "REST API versioning best practices — path prefix vs header"
    # tira crases: `/v1` e `Accept` viram sem backtick
    assert "`" not in qs[1]
    assert qs[2].startswith("API deprecation policy")


def test_extract_seed_queries_vazio_sem_bloco() -> None:
    assert extract_seed_queries("## Escopo\n- nada de pesquisa aqui") == []


async def test_tavily_search_usa_fetch_injetado() -> None:
    calls: list[dict] = []

    async def fake_fetch(url: str, payload: dict) -> dict:
        calls.append(payload)
        return {"results": [{"title": "T1", "url": "http://x/1", "content": "trecho um"}]}

    res = await tavily_search("minha query", api_key="tvly-k", fetch=fake_fetch)
    assert res[0]["url"] == "http://x/1"
    assert calls[0] == {"api_key": "tvly-k", "query": "minha query", "max_results": 3}


async def test_tavily_search_degrada_em_erro() -> None:
    async def boom(url: str, payload: dict) -> dict:
        raise RuntimeError("rede caiu")

    assert await tavily_search("q", api_key="k", fetch=boom) == []


async def test_research_block_monta_fontes_citaveis() -> None:
    async def fake_fetch(url: str, payload: dict) -> dict:
        q = payload["query"]
        return {"results": [{"title": f"Fonte de {q[:10]}", "url": "http://doc", "content": "x"}]}

    block = await research_block(
        "Definir convenção de versão", _BODY_COM_BLOCO, tavily_key="k", fetch=fake_fetch
    )
    assert block.startswith("## Fontes")
    assert "http://doc" in block
    assert "### REST API versioning best practices" in block  # 1ª query seed virou subtítulo


async def test_research_block_usa_query_gen_sem_bloco() -> None:
    async def gen(title: str, body: str) -> list[str]:
        return ["query gerada por llm"]

    async def fake_fetch(url: str, payload: dict) -> dict:
        return {"results": [{"title": "T", "url": "http://g", "content": "c"}]}

    block = await research_block(
        "Tema", "corpo sem bloco, mas precisamos pesquisar", tavily_key="k",
        fetch=fake_fetch, query_gen=gen,
    )
    assert "### query gerada por llm" in block
    assert "http://g" in block


async def test_research_block_vazio_sem_chave() -> None:
    assert await research_block("t", "b", tavily_key="") == ""


# --- gate em 2 degraus (keyword + Jev/decider) ---------------------------------------------------


async def test_critico_com_decider_consulta_jev_mesmo_sem_keyword() -> None:
    # AFROUXADO: com Jev, QUALQUER issue é avaliada — keyword não é mais pré-gate duro
    called = {"n": 0}

    class Spy:
        async def decide(self, q: str, c: str) -> Result[Decision, Error]:
            called["n"] += 1
            return Ok(Decision(True, 1.0))

    assert await research_is_critical("Corrigir bug", "ajustar split", decider=Spy())
    assert called["n"] == 1


async def test_critico_sem_decider_sem_sinal_nao_pesquisa() -> None:
    # sem Jev: keyword decide — sem sinal, não pesquisa
    assert not await research_is_critical("Corrigir bug", "ajustar split", decider=None)


async def test_critico_sem_decider_cai_no_keyword() -> None:
    assert await research_is_critical("Definir convenção de versão", "corpo", decider=None)


async def test_critico_jev_diz_nao() -> None:
    dec = _StubDecider(Ok(Decision(decision=False, confidence=0.8, reason="trade-off conhecido")))
    assert not await research_is_critical("Definir convenção de versão", "corpo", decider=dec)


async def test_critico_jev_diz_sim_com_confianca() -> None:
    dec = _StubDecider(Ok(Decision(decision=True, confidence=0.9)))
    assert await research_is_critical("Definir convenção de versão", "corpo", decider=dec)


async def test_critico_jev_sim_mas_confianca_baixa_nao_pesquisa() -> None:
    dec = _StubDecider(Ok(Decision(decision=True, confidence=0.4)))
    assert not await research_is_critical(
        "Definir convenção de versão", "corpo", decider=dec, min_confidence=0.6
    )


async def test_critico_jev_erro_cai_no_keyword() -> None:
    dec = _StubDecider(Err(Error("jev", "falhou")))
    # Jev falhou + título tem sinal ("convenção") → cai no keyword = True
    assert await research_is_critical("Definir convenção de versão", "corpo", decider=dec)


async def test_critico_jev_erro_sem_sinal_nao_pesquisa() -> None:
    dec = _StubDecider(Err(Error("jev", "falhou")))
    # Jev falhou + sem sinal → keyword = False (degrada sem forçar pesquisa)
    assert not await research_is_critical("Corrigir bug", "ajustar split", decider=dec)
