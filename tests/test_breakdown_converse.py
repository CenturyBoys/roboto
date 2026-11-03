"""Modo breakdown conversacional do refiner (incremento 2): pergunta ou propõe N esqueletos."""

from __future__ import annotations

from roboto.agents.refiner import BREAKDOWN_SYSTEM, breakdown_converse
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class _Gw:
    """Gateway stub que guarda as mensagens recebidas e devolve uma reply fixa (ou Err)."""

    def __init__(self, reply: str = "", err: Error | None = None) -> None:
        self._reply = reply
        self._err = err
        self.seen: list[ChatMessage] = []

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        self.seen = messages
        if self._err is not None:
            return Err(self._err)
        return Ok(Completion(text=self._reply, model="stub"))


async def test_pergunta_quando_falta_info() -> None:
    gw = _Gw(reply="PERGUNTA: qual o escopo do logger — os 3 apps ou só o worker?")
    step = await breakdown_converse([("user", "destrincha o épico de logging PII-safe")], gw)
    assert isinstance(step, Ok)
    assert step.value.breakdown is None
    assert step.value.question is not None
    assert "escopo do logger" in step.value.question


async def test_propoe_n_esqueletos_encadeados() -> None:
    reply = (
        "ITEM: ADR + regra no AGENTS.md\n"
        "- escrever ADR\n"
        "ITEM: logger com redaction de PII\n"
        "- mascarar email/telefone/token\n"
        "ITEM: gate pnpm check:logs\n"
        "- varrer logs no CI\n"
    )
    gw = _Gw(reply=reply)
    step = await breakdown_converse([("user", "quebra o épico #66")], gw)
    assert isinstance(step, Ok)
    assert step.value.question is None
    bd = step.value.breakdown
    assert bd is not None
    assert [i.title for i in bd.items][0] == "ADR + regra no AGENTS.md"
    assert len(bd.items) == 3
    # encadeamento: 1º independente, demais dependem do anterior
    assert [i.depends_on_prev for i in bd.items] == [False, True, True]


async def test_system_instrui_pesquisa_web() -> None:
    # o contrato do prompt precisa pedir pesquisa na web + citar fonte (requisito do usuário)
    assert "PESQUISE na web" in BREAKDOWN_SYSTEM
    assert "fonte" in BREAKDOWN_SYSTEM.lower()


async def test_transcript_vai_pro_gateway_apos_o_system() -> None:
    gw = _Gw(reply="ITEM: x\n- p\n")
    await breakdown_converse([("user", "a"), ("assistant", "PERGUNTA: b"), ("user", "c")], gw)
    assert gw.seen[0].role == "system"
    assert gw.seen[0].content == BREAKDOWN_SYSTEM
    assert [m.content for m in gw.seen[1:]] == ["a", "PERGUNTA: b", "c"]


async def test_err_do_gateway_propaga() -> None:
    gw = _Gw(err=Error("llm", "timeout"))
    step = await breakdown_converse([("user", "x")], gw)
    assert isinstance(step, Err)
    assert step.error.kind == "llm"
