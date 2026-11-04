"""Adapter JevDecider (porta Decider degrau-2): parse de saída estruturada + erros viram Err."""

from __future__ import annotations

from roboto.llm.jev import JevDecider
from roboto.result import Err, Ok


def _resp(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"content": content}}], "model": "typesafe/jev-router"}


async def test_jev_parseia_decisao_estruturada() -> None:
    async def fake_fetch(payload: dict[str, object]) -> dict[str, object]:
        # confere que pediu saída estruturada
        assert payload["response_format"]  # type: ignore[index]
        return _resp('{"decision": false, "confidence": 0.8, "reason": "trade-off conhecido"}')

    jev = JevDecider(api_key="k", fetch=fake_fetch)
    res = await jev.decide("precisa pesquisar?", "contexto da issue")
    assert isinstance(res, Ok)
    assert res.value.decision is False
    assert res.value.confidence == 0.8
    assert "trade-off" in res.value.reason


async def test_jev_erro_de_rede_vira_err() -> None:
    async def boom(payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("timeout")

    res = await JevDecider(api_key="k", fetch=boom).decide("q", "c")
    assert isinstance(res, Err)


async def test_jev_conteudo_ilegivel_vira_err() -> None:
    async def bad(payload: dict[str, object]) -> dict[str, object]:
        return _resp("isto não é json")

    res = await JevDecider(api_key="k", fetch=bad).decide("q", "c")
    assert isinstance(res, Err)
