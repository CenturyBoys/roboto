"""Gateway real sobre OpenRouter (substrato de modelos — I/L).

Mapeia tier -> modelo (chinês barato / judge / Claude frontier); pinável por medição (D16).
Não é exercitado no CI (precisa de chave); é validado por mypy/ruff e por smoke manual com token.
"""

from __future__ import annotations

import httpx

from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.llm.routing import DEFAULT_MODELS, build_routing
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result


class OpenRouterGateway:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        # roteamento tier → CADEIA de modelos (primário + fallback). Precede `models` (compat).
        routing: dict[Tier, tuple[str, ...]] | None = None,
        models: dict[Tier, str] | None = None,  # compat: 1 modelo por tier (vira cadeia de 1)
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        if routing is not None:
            self._routing = routing
        elif models is not None:
            self._routing = {t: (m,) for t, m in models.items()}
        else:
            self._routing = build_routing()
        self._client = client
        self._timeout = timeout

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        chain = self._routing.get(tier) or (DEFAULT_MODELS[tier],)
        headers = {"Authorization": f"Bearer {self._key}"}
        owns = self._client is None
        client = (
            self._client if self._client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        last: Exception | None = None
        try:
            for model in chain:  # tenta o primário; cai pro fallback do MESMO tier se der erro (I)
                payload: dict[str, object] = {
                    "model": model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                }
                # Juiz DETERMINÍSTICO: sem temperatura o OpenRouter amostra e o MESMO diff dá
                # vereditos diferentes (PoC). temp=0 fixa. Geradores (impl/chat) ficam no default.
                if tier is Tier.JUDGE:
                    payload["temperature"] = 0
                try:
                    resp = await client.post(
                        f"{self._base}/chat/completions", json=payload, headers=headers
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError as exc:
                    last = exc  # tenta o próximo modelo da cadeia
                    continue
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
        finally:
            if owns:
                await client.aclose()
        return Err(Error("model", f"openrouter: todos os modelos do tier {tier} falharam: {last}"))
