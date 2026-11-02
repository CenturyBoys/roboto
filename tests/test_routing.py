"""Roteamento tier→modelo + fallback do gateway (Trilha I)."""

from __future__ import annotations

import httpx

from roboto.llm.openrouter import OpenRouterGateway
from roboto.llm.port import ChatMessage, Tier
from roboto.llm.routing import DEFAULT_MODELS, build_routing
from roboto.result import Err, Ok


def test_no_override_is_single_default_chain() -> None:
    r = build_routing()
    assert r[Tier.CHEAP] == (DEFAULT_MODELS[Tier.CHEAP],)
    assert r[Tier.FRONTIER] == (DEFAULT_MODELS[Tier.FRONTIER],)


def test_override_prepends_and_keeps_default_as_fallback() -> None:
    r = build_routing(judge="deepseek/deepseek-r1")
    assert r[Tier.JUDGE] == ("deepseek/deepseek-r1", DEFAULT_MODELS[Tier.JUDGE])


def test_override_equal_to_default_does_not_duplicate() -> None:
    r = build_routing(frontier=DEFAULT_MODELS[Tier.FRONTIER])
    assert r[Tier.FRONTIER] == (DEFAULT_MODELS[Tier.FRONTIER],)


def _gateway(
    transport: httpx.MockTransport, routing: dict[Tier, tuple[str, ...]]
) -> OpenRouterGateway:
    client = httpx.AsyncClient(transport=transport, base_url="http://x")
    return OpenRouterGateway("k", routing=routing, client=client)


async def test_falls_back_to_second_model_on_error() -> None:
    # o primeiro modelo da cadeia erra (500); o gateway cai pro segundo e responde.
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        model = json.loads(request.content)["model"]
        if model == "primario/ruim":
            return httpx.Response(500, json={"error": "down"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "model": model,
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            },
        )

    routing = {Tier.JUDGE: ("primario/ruim", "fallback/bom")}
    gw = _gateway(httpx.MockTransport(handler), routing)
    res = await gw.complete([ChatMessage(role="user", content="oi")], Tier.JUDGE)
    assert isinstance(res, Ok)
    assert res.value.model == "fallback/bom"  # usou o fallback


async def test_all_models_fail_returns_err() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    gw = _gateway(httpx.MockTransport(handler), {Tier.CHEAP: ("a/x", "b/y")})
    res = await gw.complete([ChatMessage(role="user", content="oi")], Tier.CHEAP)
    assert isinstance(res, Err)
    assert "falharam" in res.error.message


async def test_judge_sends_temperature_zero() -> None:
    import json

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["temp"] = body.get("temperature")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "v"}}],
                "model": body["model"],
                "usage": {},
            },
        )

    gw = _gateway(httpx.MockTransport(handler), build_routing())
    await gw.complete([ChatMessage(role="user", content="x")], Tier.JUDGE)
    assert seen["temp"] == 0  # juiz determinístico
