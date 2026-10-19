"""Config do sistema — como os valores chegam ao `roboto` (D4/D17).

Fluxo: **ansible-vault** (prod) ou `.env`/compose (dev) → **variáveis de ambiente** → `load_config`
→ `Config` tipado. 1 instância por empresa (D17) ⇒ **um `tenant` por processo**. Nada de segredo no
código; aqui só lemos e validamos. Carregamento retorna `Result` (D1): faltou variável obrigatória
→ `Err` listando o que falta (o "passo de configuração" antes do teste ao vivo).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


@dataclass(frozen=True)
class GithubConfig:
    app_id: str
    private_key: str
    installation_id: str
    webhook_secret: str


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    allowlist: frozenset[str]  # user IDs autorizados (D21/M); vazio = ninguém até configurar


@dataclass(frozen=True)
class ModelsConfig:
    openrouter_api_key: str
    stt_api_key: str
    stt_base_url: str = "https://api.openai.com/v1"


@dataclass(frozen=True)
class Config:
    tenant: str
    database_url: str
    default_repo: str  # repo-alvo das issues do refino (owner/name)
    github: GithubConfig
    telegram: TelegramConfig
    models: ModelsConfig
    lease_seconds: int = 300
    console_token: str = ""  # bearer do console web (D25); vazio = console desabilitado


_REQUIRED = (
    "ROBOTO_TENANT",
    "DATABASE_URL",
    "ROBOTO_DEFAULT_REPO",
    "GITHUB_APP_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_WEBHOOK_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "OPENROUTER_API_KEY",
    "STT_API_KEY",
)


def _allowlist(raw: str) -> frozenset[str]:
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


def load_config(env: Mapping[str, str]) -> Result[Config, Error]:
    """Monta o `Config` a partir de um mapa de ambiente (injetável em teste)."""
    missing = [k for k in _REQUIRED if not env.get(k)]
    if missing:
        return Err(Error("config", f"variáveis ausentes: {', '.join(missing)}"))

    lease_raw = env.get("LEASE_SECONDS", "300")
    if not lease_raw.isdigit():
        return Err(Error("config", f"LEASE_SECONDS inválido: {lease_raw!r}"))

    return Ok(
        Config(
            tenant=env["ROBOTO_TENANT"],
            database_url=env["DATABASE_URL"],
            default_repo=env["ROBOTO_DEFAULT_REPO"],
            github=GithubConfig(
                app_id=env["GITHUB_APP_ID"],
                # tolera PEM em uma linha (\n escapado) vindo do vault/env
                private_key=env["GITHUB_APP_PRIVATE_KEY"].replace("\\n", "\n"),
                installation_id=env["GITHUB_APP_INSTALLATION_ID"],
                webhook_secret=env["GITHUB_WEBHOOK_SECRET"],
            ),
            telegram=TelegramConfig(
                bot_token=env["TELEGRAM_BOT_TOKEN"],
                allowlist=_allowlist(env.get("TELEGRAM_ALLOWLIST", "")),
            ),
            models=ModelsConfig(
                openrouter_api_key=env["OPENROUTER_API_KEY"],
                stt_api_key=env["STT_API_KEY"],
                stt_base_url=env.get("STT_BASE_URL", "https://api.openai.com/v1"),
            ),
            lease_seconds=int(lease_raw),
            console_token=env.get("CONSOLE_TOKEN", ""),
        )
    )
