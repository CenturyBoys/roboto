"""SessionHub (trilha O, Fatia 5): fila de steer, Future de aprovação, interrupt — em processo."""

from __future__ import annotations

from roboto.app.session_hub import SessionHub


async def test_open_get_close() -> None:
    hub = SessionHub()
    assert hub.get(1) is None
    live = hub.open(1)
    assert hub.get(1) is live
    hub.close(1)
    assert hub.get(1) is None


async def test_steer_queue_fifo() -> None:
    live = SessionHub().open(7)
    await live.steer("primeira")
    await live.steer("segunda")
    assert live.has_input() is True
    assert await live.next_input() == "primeira"
    assert await live.next_input() == "segunda"


async def test_approval_future_resolves() -> None:
    live = SessionHub().open(3)
    fut = live.request_approval(42)
    assert fut.done() is False
    assert live.resolve_approval(42, True) is True  # havia alguém esperando
    assert fut.result() is True
    assert live.resolve_approval(42, True) is False  # já consumido


async def test_interrupt_flag() -> None:
    live = SessionHub().open(9)
    assert live.interrupt_requested is False
    live.request_interrupt()
    assert live.interrupt_requested is True
