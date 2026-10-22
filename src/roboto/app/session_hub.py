"""Registro de sessões VIVAS do motor (trilha O, Fatia 5 — co-piloto).

O console (HTTP) e o driver do motor rodam no MESMO event-loop do daemon, mas o console não tem como
alcançar um motor em execução p/ (a) mandar uma mensagem no meio (steer) e (b) entregar uma decisão
de aprovação que o callback `can_use_tool` está aguardando. Este hub resolve isso **em processo**:

- `steer(text)`: enfileira uma mensagem humana p/ o driver consumir após a resposta atual.
- `request_approval(interaction_id)`: o driver cria um `Future` que o `can_use_tool` aguarda; o
  console/Telegram resolve com `resolve_approval(...)` quando o humano responde.
- `request_interrupt()`: sinaliza cancelamento; o driver chama `client.interrupt()`.

É efêmero (vive só enquanto a sessão está rodando) e single-loop (um daemon, um event-loop) — por
isso `Future`/`Queue` simples bastam, sem lock. Estado durável continua no banco (determinismo).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class LiveSession:
    execution_id: int
    _inbox: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    _approvals: dict[int, asyncio.Future[bool]] = field(default_factory=dict)
    _interrupt: asyncio.Event = field(default_factory=asyncio.Event)
    _ended: asyncio.Event = field(default_factory=asyncio.Event)

    async def steer(self, text: str) -> None:
        await self._inbox.put(text)

    async def next_input(self) -> str | None:
        """Próxima mensagem humana entre turnos; `None` se a sessão foi encerrada (parar)."""
        getter: asyncio.Task[str] = asyncio.ensure_future(self._inbox.get())
        ender: asyncio.Task[bool] = asyncio.ensure_future(self._ended.wait())
        done, pending = await asyncio.wait({getter, ender}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if getter in done and not getter.cancelled():
            return getter.result()
        return None

    def has_input(self) -> bool:
        return not self._inbox.empty()

    def request_end(self) -> None:
        self._ended.set()

    @property
    def ended(self) -> bool:
        return self._ended.is_set()

    def request_approval(self, interaction_id: int) -> asyncio.Future[bool]:
        """Driver: cria o Future que o `can_use_tool` vai aguardar (allow=True/deny=False)."""
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._approvals[interaction_id] = fut
        return fut

    def resolve_approval(self, interaction_id: int, approved: bool) -> bool:
        """Console/Telegram: entrega a decisão humana. Retorna True se havia alguém esperando."""
        fut = self._approvals.pop(interaction_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(approved)
        return True

    def request_interrupt(self) -> None:
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        self._interrupt.clear()

    @property
    def interrupt_requested(self) -> bool:
        return self._interrupt.is_set()

    async def wait_control(self) -> None:
        """Desbloqueia no INSTANTE em que interromper OU encerrar é pedido (fora do loop de stream),
        pra o driver cortar o motor na hora — controles de parada são prioridade máxima."""
        waiters = [
            asyncio.ensure_future(self._interrupt.wait()),
            asyncio.ensure_future(self._ended.wait()),
        ]
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in waiters:
                w.cancel()


class SessionHub:
    """Mapa execução→sessão viva. Compartilhado entre o driver do motor e o console."""

    def __init__(self) -> None:
        self._live: dict[int, LiveSession] = {}

    def open(self, execution_id: int) -> LiveSession:
        live = LiveSession(execution_id=execution_id)
        self._live[execution_id] = live
        return live

    def get(self, execution_id: int) -> LiveSession | None:
        return self._live.get(execution_id)

    def close(self, execution_id: int) -> None:
        self._live.pop(execution_id, None)
