"""`python -m roboto` -> sobe o daemon (servidor ASGI + laços)."""

from __future__ import annotations

import asyncio

from roboto.runtime import main

raise SystemExit(asyncio.run(main()))
