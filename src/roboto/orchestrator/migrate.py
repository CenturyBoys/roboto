"""Aplica migrations pendentes no boot do daemon (#276).

O schema é criado pelo **initdb** do Postgres só no 1º boot do volume — então uma migration nova num
banco **já existente** não se aplica sozinha (incidente 2026-11-19: `config_hash`/`breakdown_draft`
faltando → erro em runtime). Este runner roda no boot: registra o que já aplicou em
`schema_migrations` e aplica, em ordem, os `.sql` que faltam. As migrations são **idempotentes**
(IF NOT EXISTS), então re-rodar uma já aplicada é no-op seguro — e um banco criado via initdb é
simplesmente registrado (baseline) sem efeito colateral.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# migrations/ na raiz do repo (copiada pra imagem em /app/migrations — ver Dockerfile).
_DEFAULT_DIR = Path(__file__).resolve().parents[3] / "migrations"


def pending_migrations(all_files: list[str], applied: set[str]) -> list[str]:
    """Nomes de migration ainda não aplicados, em ordem lexical (0001, 0002, …). Puro."""
    return [name for name in sorted(all_files) if name not in applied]


async def apply_migrations(pool: Any, migrations_dir: Path | None = None) -> list[str]:
    """Aplica as migrations pendentes e devolve os nomes aplicados nesta rodada (pode ser vazio)."""
    directory = migrations_dir or _DEFAULT_DIR
    files = [path.name for path in directory.glob("*.sql")]
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        rows = await conn.fetch("SELECT filename FROM schema_migrations")
        applied = {row["filename"] for row in rows}
        done: list[str] = []
        for name in pending_migrations(files, applied):
            sql = (directory / name).read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)  # idempotente (IF NOT EXISTS); DDL em batch
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1) ON CONFLICT DO NOTHING",
                    name,
                )
            done.append(name)
        return done
