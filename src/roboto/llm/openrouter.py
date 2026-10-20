"""Gateway real sobre OpenRouter (substrato de modelos — I/L).

Mapeia tier -> modelo (chinês barato / judge / Claude frontier); pinável por medição (D16).
Não é exercitado no CI (precisa de chave); é validado por mypy/ruff e por smoke manual com token.
"""

from __future__ import annotations

import httpx

from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

# Mix pinado por medição (D16): Qwen via OpenRouter. big=qwen3-coder, small=qwen2.5 (ver N3/PoC).
_DEFAULT_MODELS: dict[Tier, str] = {
    Tier.CHEAP: "qwen/qwen-2.5-72b-instruct",
    Tier.JUDGE: "qwen/qwen-2.5-72b-instruct",
    Tier.FRONTIER: "qwen/qwen3-coder",
}


class OpenRouterGateway:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        models: dict[Tier, str] | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._models = models or dict(_DEFAULT_MODELS)
        self._client = client
        self._timeout = timeout

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        model = self._models[tier]
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        try:
            resp = await client.post(
                f"{self._base}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return Err(Error("model", f"openrouter: {exc}"))
        finally:
            if owns:
                await client.aclose()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return Ok(
            Completion(
                text=str(text),
                model=str(data.get("model", model)),
                tokens_in=int(usage.get("prompt_tokens", 0)),
                tokens_out=int(usage.get("completion_tokens", 0)),
            )
        )
