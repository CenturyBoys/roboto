"""Composição: `Config` -> adapters prontos (o ponto onde a config vira sistema).

Puro wiring, sem rede: instancia gateway de modelo, STT, cliente GitHub App, canal Telegram e o
`RouterPublisher` do outbox (kind -> handler). O Store (Postgres) é criado à parte (é async e tem
ciclo de vida próprio). Trocar provedor/canal = trocar aqui, não no núcleo.
"""

from __future__ import annotations

from dataclasses import dataclass

from roboto.app.effects import GithubIssuePublisher, TelegramPublisher
from roboto.channels.telegram import TelegramChannel
from roboto.config import Config
from roboto.github.app import GithubAppClient
from roboto.llm.openrouter import OpenRouterGateway
from roboto.llm.stt import WhisperTranscriber
from roboto.orchestrator.runner import RouterPublisher


@dataclass(frozen=True)
class Adapters:
    gateway: OpenRouterGateway
    transcriber: WhisperTranscriber
    github: GithubAppClient
    channel: TelegramChannel
    router: RouterPublisher


def build_adapters(config: Config) -> Adapters:
    gateway = OpenRouterGateway(config.models.openrouter_api_key)
    transcriber = WhisperTranscriber(
        config.models.stt_api_key, base_url=config.models.stt_base_url
    )
    github = GithubAppClient(
        app_id=config.github.app_id,
        private_key=config.github.private_key,
        installation_id=config.github.installation_id,
    )
    channel = TelegramChannel(
        config.telegram.bot_token,
        config.tenant,
        allowlist=set(config.telegram.allowlist),
    )
    router = RouterPublisher(
        {
            "create_issue": GithubIssuePublisher(github),
            "telegram_notify": TelegramPublisher(channel),
        }
    )
    return Adapters(
        gateway=gateway,
        transcriber=transcriber,
        github=github,
        channel=channel,
        router=router,
    )
