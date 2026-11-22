"""Módulo do gerente (escada worker→gerente→humano, fatia 1 do épico #322)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from roboto.app.manager import manager_prompt, run_manager
from roboto.engines.port import EngineEvent, EngineEventKind, RunSpec
from roboto.orchestrator.model import Engine, Error
from roboto.result import Err, Ok, Result


def test_manager_prompt_tem_mandato_de_supervisor() -> None:
    p = manager_prompt("typecheck", "error TS2322 ...", "feat(core): bracket", "corpo da issue")
    assert "SENIOR ENGINEER" in p or "MANAGER" in p
    assert "typecheck" in p  # cita o gate que reprovou
    assert "error TS2322" in p  # inclui a saída vermelha
    assert "human DECISION" in p  # só escala pro humano se precisar de DECISÃO humana
    assert "Do NOT weaken" in p  # não pode gutar teste pra passar


class _FakeMgr:
    """Motor-gerente fake: registra que rodou; devolve um script de eventos."""

    def __init__(self, fail_start: bool = False) -> None:
        self.started = False
        self._fail = fail_start

    @property
    def engine(self) -> Engine:
        return Engine.CLAUDE_CODE

    async def start(self, spec: RunSpec) -> Result[str, Error]:
        if self._fail:
            return Err(Error("engine", "não iniciou"))
        self.started = True
        return Ok("sess")

    async def events(self) -> AsyncIterator[EngineEvent]:
        yield EngineEvent(EngineEventKind.MESSAGE, text="consertando…")
        yield EngineEvent(EngineEventKind.FINISHED)


async def test_run_manager_arranca_o_motor() -> None:
    mgr = _FakeMgr()
    ok = await run_manager(
        lambda: mgr, tenant="acme", repo="acme/app", workdir="/w", prompt="resolva",
    )
    assert ok is True
    assert mgr.started is True


async def test_run_manager_false_se_motor_nao_inicia() -> None:
    ok = await run_manager(
        lambda: _FakeMgr(fail_start=True), tenant="acme", repo="acme/app", workdir="/w",
        prompt="resolva",
    )
    assert ok is False
