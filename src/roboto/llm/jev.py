"""Adapter do Jev (TypeSafe System One) sobre OpenRouter — implementação da porta `Decider`.

Jev é o **degrau-2**: decisão tipada + confiança calibrada. Alcançável via OpenRouter
(`typesafe/jev-router`, usa a `OPENROUTER_API_KEY`); pede saída estruturada (`response_format`
json_schema) e parseia `{decision, confidence, reason}`. HTTP **injetável** (`fetch`) → testável sem
rede. Qualquer erro vira `Err` — o consumidor degrada para o fallback (nunca bloqueia).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from roboto.llm.decide import Decision
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

# fetch: payload do chat/completions -> json de resposta. Injetável; default usa httpx (runtime).
JevFetch = Callable[[dict[str, object]], Awaitable[dict[str, object]]]

_SYSTEM = (
    "Você é um decisor. Responda SOMENTE o JSON do schema: decision (bool), confidence (0..1 "
    "calibrada) e reason (curto). Conservador: 'decision=true' só quando realmente justificado."
)

_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "decision": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["decision", "confidence", "reason"],
    "additionalProperties": False,
}


class JevDecider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "typesafe/jev-router",
        fetch: JevFetch | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
    ) -> None:
        self._key = api_key
        self._model = model
        self._fetch = fetch
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _http(self, payload: dict[str, object]) -> dict[str, object]:
        import httpx  # import tardio: só runtime precisa

        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else {}

    async def decide(self, question: str, context: str) -> Result[Decision, Error]:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"{question}\n\nContexto:\n{context}"},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "decision", "strict": True, "schema": _SCHEMA},
            },
            "max_tokens": 600,
        }
        do_fetch = self._fetch or self._http
        try:
            data = await do_fetch(payload)
        except Exception as exc:  # noqa: BLE001 — rede/provedor: vira Err, consumidor faz fallback
            return Err(Error("jev", f"chamada ao Jev falhou: {exc}"))
        return _parse(data)


def _parse(data: dict[str, object]) -> Result[Decision, Error]:
    try:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return Err(Error("jev", "resposta do Jev sem choices"))
        content = choices[0]["message"]["content"]
        obj = json.loads(content)
        return Ok(
            Decision(
                decision=bool(obj["decision"]),
                confidence=float(obj["confidence"]),
                reason=str(obj.get("reason", "")),
            )
        )
    except (KeyError, ValueError, TypeError) as exc:
        return Err(Error("jev", f"resposta do Jev ilegível: {exc}"))
