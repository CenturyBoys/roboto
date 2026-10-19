"""GitHub App client — caminho REST de criar issue via httpx.MockTransport (token injetado)."""

from __future__ import annotations

import httpx

from roboto.github.app import GithubAppClient
from roboto.result import Err, Ok


async def test_create_issue_parses_ref() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/repos/acme/app/issues")
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(
            201, json={"number": 142, "html_url": "https://github.com/acme/app/issues/142"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        gh = GithubAppClient(
            app_id="1", private_key="", installation_id="1", client=client, token="tok"
        )
        result = await gh.create_issue("acme/app", "Título", "Corpo")
        assert isinstance(result, Ok)
        assert result.value.number == 142
        assert result.value.url.endswith("/issues/142")
        assert result.value.repo == "acme/app"
    finally:
        await client.aclose()


async def test_create_issue_http_error_is_err() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Validation Failed"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        gh = GithubAppClient(
            app_id="1", private_key="", installation_id="1", client=client, token="tok"
        )
        result = await gh.create_issue("acme/app", "t", "b")
        assert isinstance(result, Err)
        assert result.error.kind == "github"
    finally:
        await client.aclose()
