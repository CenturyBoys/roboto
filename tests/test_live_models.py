"""Switcher de modelo por etapa (hot-reload): persiste no app_config e aplica em memória."""

from __future__ import annotations

from datetime import UTC, datetime

from roboto.app.live_models import STAGES, LiveModels
from roboto.engines.claude_code import ClaudeCodeEngine
from roboto.llm.openrouter import OpenRouterGateway
from roboto.llm.port import Tier
from roboto.orchestrator.store import InMemoryStore


def _now() -> datetime:
    return datetime(2026, 11, 18, tzinfo=UTC)


async def test_snapshot_lista_as_7_etapas() -> None:
    lm = LiveModels(InMemoryStore(), OpenRouterGateway("k"), _now, {})
    snap = lm.snapshot()
    assert [s["key"] for s in snap] == [st.key for st in STAGES]
    cheap = next(s for s in snap if s["key"] == "CHEAP_MODEL")
    assert cheap["effective"] == "qwen/qwen-2.5-72b-instruct"  # default do tier
    jev = next(s for s in snap if s["key"] == "JEV_MODEL")
    assert jev["live"] is False  # decisor construído no boot → vale no próximo restart


async def test_troca_cheap_hot_reload_no_gateway_e_persiste() -> None:
    store = InMemoryStore()
    gw = OpenRouterGateway("k")
    lm = LiveModels(store, gw, _now, {})
    snap = await lm.set_models({"CHEAP_MODEL": "qwen/qwen3.8-flash"})
    # gateway já usa o novo modelo na próxima chamada (sem restart)
    assert gw._routing[Tier.CHEAP][0] == "qwen/qwen3.8-flash"
    # persistiu no app_config (fonte única)
    assert (await store.get_app_config())["CHEAP_MODEL"] == "qwen/qwen3.8-flash"
    assert next(s for s in snap if s["key"] == "CHEAP_MODEL")["value"] == "qwen/qwen3.8-flash"


async def test_troca_motor_chama_set_model() -> None:
    eng = ClaudeCodeEngine(model="base")
    lm = LiveModels(InMemoryStore(), OpenRouterGateway("k"), _now, {})
    lm.register_engine("impl", eng)
    await lm.set_models({"ROBOTO_ENGINE_MODEL": "qwen/qwen3.8-27b"})
    assert eng._model == "qwen/qwen3.8-27b"


async def test_valor_vazio_volta_ao_default() -> None:
    gw = OpenRouterGateway("k")
    lm = LiveModels(InMemoryStore(), gw, _now, {"CHEAP_MODEL": "qwen/qwen3.8-flash"})
    await lm.set_models({"CHEAP_MODEL": ""})
    assert gw._routing[Tier.CHEAP] == ("qwen/qwen-2.5-72b-instruct",)  # cadeia de 1 = só o default


async def test_chave_desconhecida_ignorada() -> None:
    store = InMemoryStore()
    lm = LiveModels(store, OpenRouterGateway("k"), _now, {})
    await lm.set_models({"FOO": "bar"})
    assert "FOO" not in (await store.get_app_config())
