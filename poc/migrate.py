"""Aplica as migrações (idempotente, SEM truncar) — o entrypoint roda antes do daemon da Fase 1."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

_MIGRATIONS = sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql"))


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[migrate] DATABASE_URL não definido")
        return 1
    conn = await asyncpg.connect(dsn)
    try:
        for migration in _MIGRATIONS:
            await conn.execute(migration.read_text())
    finally:
        await conn.close()
    print(f"[migrate] {len(_MIGRATIONS)} migração(ões) aplicada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
