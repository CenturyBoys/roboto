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


def test_review_nunca_e_o_mesmo_modelo_do_escritor() -> None:
    # P1a: por default JUDGE == CHEAP (ambos qwen-2.5-72b) → o guard promove o review p/ FRONTIER,
    # pra o revisor NUNCA ser tão fraco quanto o escritor (bug do run-1047).
    r = build_routing()
    assert r[Tier.JUDGE][0] != r[Tier.CHEAP][0]
    assert r[Tier.JUDGE] == r[Tier.FRONTIER]  # promovido pro tier forte


def test_judge_explicito_distinto_vence_o_guard() -> None:
    # operador aponta o review p/ um modelo forte específico (ex.: Sonnet) → respeita, não promove.
    r = build_routing(judge="anthropic/claude-sonnet-4.6")
    assert r[Tier.JUDGE] == ("anthropic/claude-sonnet-4.6", DEFAULT_MODELS[Tier.JUDGE])


def test_guard_dispara_quando_cheap_e_judge_sao_iguais_por_override() -> None:
    # se alguém setar judge == cheap explicitamente, ainda assim promove (revisor ≠ escritor).
    r = build_routing(cheap="x/model", judge="x/model", frontier="y/forte")
    assert r[Tier.JUDGE] == r[Tier.FRONTIER]  # promovido pro tier forte (com seu fallback)
    assert r[Tier.JUDGE][0] == "y/forte" and r[Tier.JUDGE][0] != r[Tier.CHEAP][0]


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


async def test_max_tokens_cap_in_payload() -> None:
    # L/K: o cap de max_tokens entra no payload (reduz a reserva upfront → evita 402 em request)
    import json

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["max_tokens"] = body.get("max_tokens")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "v"}}], "model": body["model"], "usage": {}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x")
    gw = OpenRouterGateway("k", routing=build_routing(), max_tokens=8192, client=client)
    await gw.complete([ChatMessage(role="user", content="x")], Tier.CHEAP)
    assert seen["max_tokens"] == 8192


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
