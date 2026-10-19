"""Cliente GitHub App (D17/D21): autentica como app -> token de instalação -> REST.

Controle fino do fluxo: permissões fine-grained, N repos por org, tokens curtos. Aqui só o
necessário para **materializar o IssueDraft numa issue** (fonte da verdade, D15/D20). Não é
exercitado no CI com credencial real; o caminho REST é testado via httpx.MockTransport injetando
um token (o JWT/troca de token precisa de chave privada real).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import jwt

from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


@dataclass(frozen=True)
class IssueRef:
    repo: str
    number: int
    url: str


class GithubAppClient:
    def __init__(
        self,
        *,
        app_id: str,
        private_key: str,
        installation_id: str,
        api_base: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
        token: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._installation_id = installation_id
        self._api = api_base.rstrip("/")
        self._client = client
        self._token = token  # injetável (teste/cache); se vazio, gera via JWT
        self._timeout = timeout

    async def create_issue(self, repo: str, title: str, body: str) -> Result[IssueRef, Error]:
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            token = await self._installation_token(client)
            resp = await client.post(
                f"{self._api}/repos/{repo}/issues",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"title": title, "body": body},
            )
            resp.raise_for_status()
            data = resp.json()
            return Ok(IssueRef(repo=repo, number=int(data["number"]), url=str(data["html_url"])))
        except httpx.HTTPError as exc:
            return Err(Error("github", f"create_issue {repo}: {exc}"))
        finally:
            if owns:
                await client.aclose()

    async def _installation_token(self, client: httpx.AsyncClient) -> str:
        if self._token:
            return self._token
        now = int(time.time())
        app_jwt = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._app_id},
            self._private_key,
            algorithm="RS256",
        )
        resp = await client.post(
            f"{self._api}/app/installations/{self._installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        self._token = str(resp.json()["token"])
        return self._token
