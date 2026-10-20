"""MeteredGateway — grava cada chamada de modelo no llm_call (medição completa, D10/L).

Wrapper drop-in de `ModelGateway`: chama o gateway real, registra tokens/custo por run, devolve o
resultado. Usado no refino (tier CHEAP) e no review (tier JUDGE) — assim a medição cobre tudo, não
só o motor. Custo a rate Qwen (afinar em L); o rótulo do provedor não é fonte de verdade.
"""

from __future__ import annotations

from datetime import datetime

from roboto.llm.port import ChatMessage, Completion, ModelGateway, Tier
from roboto.orchestrator.model import Error
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result

_COST_PER_MTOK = 0.4


class MeteredGateway:
    def __init__(
        self,
        inner: ModelGateway,
        store: Store,
        *,
        tenant: str,
        run_id: int | None,
        now: datetime,
        cost_per_mtok: float = _COST_PER_MTOK,
    ) -> None:
        self._inner = inner
        self._store = store
        self._tenant = tenant
        self._run_id = run_id
        self._now = now
        self._rate = cost_per_mtok

    async def complete(self, messages: list[ChatMessage], tier: Tier) -> Result[Completion, Error]:
        result = await self._inner.complete(messages, tier)
        if isinstance(result, Ok):
            c = result.value
            await self._store.record_llm_call(
                tenant=self._tenant,
                run_id=self._run_id,
                provider="openrouter",
                model=c.model,
                tier=str(tier),
                tokens_in=c.tokens_in,
                tokens_out=c.tokens_out,
                cost_usd=(c.tokens_in + c.tokens_out) / 1_000_000 * self._rate,
                now=self._now,
            )
        return result
