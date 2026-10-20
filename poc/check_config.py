"""Valida a config (env injetado do .env.poc) e imprime um checklist amigável. Reexecutável.

Usa o mesmo `load_config` do roboto: o que passar aqui passa no daemon. Sai 0 (ok) / 1 (falta).
"""

from __future__ import annotations

import os

from roboto.config import load_config
from roboto.result import Ok


def main() -> int:
    result = load_config(os.environ)
    if not isinstance(result, Ok):
        print("CONFIG INCOMPLETA:", result.error.message)
        return 1
    c = result.value
    gh = "PAT" if c.github.api_token else ("App" if c.github.app_id else "FALTA")
    print("CONFIG OK")
    print(f"  tenant       = {c.tenant}")
    print(f"  repo-alvo    = {c.default_repo}")
    print(f"  motor        = {c.engine or '(nenhum)'}")
    print(f"  github auth  = {gh}")
    print(
        f"  telegram     = {'ok' if c.telegram.bot_token else 'FALTA'} "
        f"(allowlist={len(c.telegram.allowlist)}, chat={c.chat_id or '-'})"
    )
    print(f"  openrouter   = {'ok' if c.models.openrouter_api_key else 'FALTA'}")
    print(f"  stt/áudio    = {'ok' if c.models.stt_api_key else '(opcional, vazio)'}")
    print(f"  console web  = {'ok' if c.console_token else '(desabilitado)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
