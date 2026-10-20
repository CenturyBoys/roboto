"""Carregamento de config a partir do ambiente (determinístico, mapa injetado)."""

from __future__ import annotations

from roboto.app.compose import build_adapters
from roboto.config import load_config
from roboto.result import Err, Ok

_FULL = {
    "ROBOTO_TENANT": "acme",
    "DATABASE_URL": "postgresql://u:p@localhost:5432/roboto",
    "ROBOTO_DEFAULT_REPO": "acme/app",
    "GITHUB_APP_ID": "123",
    "GITHUB_APP_PRIVATE_KEY": "-----BEGIN-----\\nABC\\n-----END-----",
    "GITHUB_APP_INSTALLATION_ID": "789",
    "GITHUB_WEBHOOK_SECRET": "whsec",
    "TELEGRAM_BOT_TOKEN": "000:AAA",
    "TELEGRAM_ALLOWLIST": "111, 222 ,,333",
    "OPENROUTER_API_KEY": "sk-or-x",
    "STT_API_KEY": "sk-y",
}


def test_load_full_env() -> None:
    result = load_config(_FULL)
    assert isinstance(result, Ok)
    cfg = result.value
    assert cfg.tenant == "acme"
    assert cfg.default_repo == "acme/app"
    assert cfg.lease_seconds == 300
    assert cfg.telegram.allowlist == frozenset({"111", "222", "333"})  # strip + descarta vazios
    assert "\n" in cfg.github.private_key  # \n escapado vira newline real


def test_missing_required_lists_them() -> None:
    partial = {"ROBOTO_TENANT": "acme"}
    result = load_config(partial)
    assert isinstance(result, Err)
    assert result.error.kind == "config"
    assert "DATABASE_URL" in result.error.message
    assert "OPENROUTER_API_KEY" in result.error.message


def _pat_env() -> dict[str, str]:
    """Modo PAT: sem GitHub App, só um token para git + API."""
    base = {k: v for k, v in _FULL.items() if not k.startswith("GITHUB_APP")}
    base.pop("GITHUB_WEBHOOK_SECRET", None)
    base["GITHUB_API_TOKEN"] = "github_pat_xxx"
    return base


def test_pat_mode_is_valid_without_app() -> None:
    result = load_config(_pat_env())
    assert isinstance(result, Ok)
    assert result.value.github.api_token == "github_pat_xxx"
    assert result.value.github.app_id == ""


def test_no_github_auth_is_err() -> None:
    env = _pat_env()
    env.pop("GITHUB_API_TOKEN")
    result = load_config(env)
    assert isinstance(result, Err)
    assert "GITHUB_API_TOKEN" in result.error.message


def test_invalid_lease_is_err() -> None:
    result = load_config({**_FULL, "LEASE_SECONDS": "abc"})
    assert isinstance(result, Err)
    assert "LEASE_SECONDS" in result.error.message


def test_build_adapters_from_config() -> None:
    cfg = load_config(_FULL)
    assert isinstance(cfg, Ok)
    adapters = build_adapters(cfg.value)  # só construção, sem rede
    assert "create_issue" in adapters.router._handlers
    assert "telegram_notify" in adapters.router._handlers
    assert adapters.channel._tenant == "acme"
