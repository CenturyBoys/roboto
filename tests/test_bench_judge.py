"""Juiz de benchmark auto-validado (Ponytail): self-test antes de pontuar; rubrica obrigatória."""

from __future__ import annotations

from roboto.app.bench_judge import (
    _SELFTEST_OVER,
    score_overengineering,
    selftest,
    trusted_score,
)
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class _Gw:
    """Gateway fake: mapeia (trecho do user) → resposta do juiz."""

    def __init__(self, by_marker: dict[str, str]) -> None:
        self._by = by_marker

    async def complete(self, messages: list[ChatMessage], tier: Tier) -> Result[Completion, Error]:
        user = messages[-1].content
        for marker, reply in self._by.items():
            if marker in user:
                return Ok(Completion(text=reply, model="judge"))
        return Ok(Completion(text="NOTA: 0\nCONSTRUTO: nenhum", model="judge"))


def _score(n: int, construto: str = "factory") -> str:
    return f"NOTA: {n}\nCONSTRUTO: {construto}"


async def test_score_exige_construto() -> None:
    gw = _Gw({"": "NOTA: 7"})  # sem CONSTRUTO → inválido
    r = await score_overengineering("qualquer", gw)  # type: ignore[arg-type]
    assert isinstance(r, Err) and "rubrica" in r.error.message


async def test_selftest_passa_quando_over_maior() -> None:
    gw = _Gw({"AbstractAdderFactory": _score(8), "def add": _score(1)})
    r = await selftest(gw)  # type: ignore[arg-type]
    assert isinstance(r, Ok) and r.value is True


async def test_selftest_falha_quando_juiz_nao_discrimina() -> None:
    gw = _Gw({"AbstractAdderFactory": _score(2), "def add": _score(2)})  # não discrimina
    r = await selftest(gw)  # type: ignore[arg-type]
    assert isinstance(r, Ok) and r.value is False


async def test_trusted_score_recusa_se_selftest_falha() -> None:
    # juiz que dá a mesma nota p/ tudo → self-test falha → NÃO pontua (não confia no veredito)
    gw = _Gw({"AbstractAdderFactory": _score(5), "def add": _score(5), "alvo": _score(9)})
    r = await trusted_score("alvo over-engineered", gw)  # type: ignore[arg-type]
    assert isinstance(r, Err) and "self-test" in r.error.message


async def test_trusted_score_pontua_quando_juiz_confiavel() -> None:
    # OVER (AbstractAdderFactory) antes de "def add" (que também está na ref OVER)
    gw = _Gw({"AbstractAdderFactory": _score(8), "def add": _score(1), "alvo": _score(6, "x")})
    r = await trusted_score("alvo com wrapper inútil", gw)  # type: ignore[arg-type]
    assert isinstance(r, Ok) and r.value.nota == 6.0 and r.value.construto == "x"


def test_referencia_over_tem_abstracao() -> None:
    assert "Factory" in _SELFTEST_OVER and "Strategy" in _SELFTEST_OVER  # é mesmo over-engineered
