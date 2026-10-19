"""Canais de comunicação como adapters sobre um núcleo agnóstico (D20)."""

from roboto.channels.model import InboundMessage, MessageKind, OutboundMessage
from roboto.channels.port import Channel

__all__ = ["Channel", "InboundMessage", "MessageKind", "OutboundMessage"]
