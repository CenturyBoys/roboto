"""Transporte web (ASGI): console operacional (D25). Mesmo backend do Telegram."""

from roboto.web.app import build_app
from roboto.web.console import build_console, console_routes

__all__ = ["build_app", "build_console", "console_routes"]
