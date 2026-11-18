"""Troca de modelo por ETAPA sem restart (switcher ao vivo).

Fonte única continua o ``app_config`` (trilha O): cada troca PERSISTE lá. O efeito é aplicado EM
MEMÓRIA para não derrubar runs:
- tiers do gateway (cheap/judge/frontier) → ``gateway.set_routing`` (consultado por chamada);
- motores (impl/refino) → ``engine.set_model`` (lido por run);
- STRONG → ``os.environ`` (lido por chamada em ``run_pr_cycle``).

JEV é lido por um decisor construído 1x no boot → a troca persiste e vale no **próximo restart**
(sinalizado ao operador). Determinístico e testável: sem I/O além do ``store`` injetado.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from roboto.engines.claude_code import ClaudeCodeEngine
from roboto.llm.openrouter import OpenRouterGateway
from roboto.llm.port import Tier
from roboto.llm.routing import DEFAULT_MODELS, build_routing
from roboto.orchestrator.store import Store


@dataclass(frozen=True)
class Stage:
    """Uma etapa do pipeline e a chave de config que controla seu modelo."""

    key: str
    label: str
    default: str  # default efetivo quando o override é vazio ("" = default do motor/ccr)
    live: bool  # aplica sem restart? (JEV = False — decisor construído no boot)


# ordem = ordem de exibição no cockpit
STAGES: tuple[Stage, ...] = (
    Stage("CHEAP_MODEL", "Breakdown / refino-conversa / chat", DEFAULT_MODELS[Tier.CHEAP], True),
    Stage("JUDGE_MODEL", "Review de PR / juiz do DoR", DEFAULT_MODELS[Tier.JUDGE], True),
    Stage("FRONTIER_MODEL", "Geração forte (tier frontier)", DEFAULT_MODELS[Tier.FRONTIER], True),
    Stage("REFINE_MODEL", "Refino engine-scoped (motor lê o repo)", "", True),
    Stage("ROBOTO_ENGINE_MODEL", "Implementação (motor de código)", "", True),
    Stage("ROBOTO_STRONG_MODEL", "Tier forte / resgate ao travar", "", True),
    Stage("JEV_MODEL", "Decisor degrau-2 (criticidade da pesquisa)", "", False),
)
_KEYS: frozenset[str] = frozenset(s.key for s in STAGES)


class LiveModels:
    """Aplica trocas de modelo por etapa sem restart e expõe o estado atual ao cockpit."""

    def __init__(
        self,
        store: Store,
        gateway: OpenRouterGateway,
        now: Callable[[], datetime],
        values: dict[str, str],
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._now = now
        self._values: dict[str, str] = {s.key: values.get(s.key, "") for s in STAGES}
        self._engines: dict[str, ClaudeCodeEngine] = {}  # "impl"/"refine" (registrados no boot)

    def register_engine(self, role: str, engine: ClaudeCodeEngine) -> None:
        """Liga um motor (``impl``/``refine``) ao switcher — chamado após o boot construí-lo."""
        self._engines[role] = engine

    def snapshot(self) -> list[dict[str, object]]:
        """Estado atual por etapa (p/ a UI): override salvo + modelo efetivo + se é live."""
        out: list[dict[str, object]] = []
        for s in STAGES:
            override = self._values.get(s.key, "")
            out.append(
                {
                    "key": s.key,
                    "label": s.label,
                    "default": s.default,
                    "value": override,
                    "effective": override or s.default or "(default do motor)",
                    "live": s.live,
                }
            )
        return out

    def _apply_routing(self) -> None:
        self._gateway.set_routing(
            build_routing(
                cheap=self._values.get("CHEAP_MODEL", ""),
                judge=self._values.get("JUDGE_MODEL", ""),
                frontier=self._values.get("FRONTIER_MODEL", ""),
            )
        )

    async def set_models(self, updates: dict[str, str]) -> list[dict[str, object]]:
        """Persiste as trocas (app_config) e aplica ao vivo. Chaves desconhecidas são ignoradas;
        valor vazio volta a etapa ao default. Devolve o snapshot atualizado."""
        clean = {k: v.strip() for k, v in updates.items() if k in _KEYS}
        if not clean:
            return self.snapshot()
        self._values.update(clean)
        await self._store.set_app_config(dict(clean), self._now())

        # gateway (cheap/judge/frontier) — rebuilda a cadeia de roteamento
        if clean.keys() & {"CHEAP_MODEL", "JUDGE_MODEL", "FRONTIER_MODEL"}:
            self._apply_routing()
        # motores (lidos por run)
        if "REFINE_MODEL" in clean and (eng := self._engines.get("refine")) is not None:
            eng.set_model(clean["REFINE_MODEL"])
        if "ROBOTO_ENGINE_MODEL" in clean and (eng := self._engines.get("impl")) is not None:
            eng.set_model(clean["ROBOTO_ENGINE_MODEL"])
        # lidos do env por chamada (STRONG) / no boot (ENGINE, JEV) — mantém o env coerente
        for env_key in ("ROBOTO_ENGINE_MODEL", "ROBOTO_STRONG_MODEL", "JEV_MODEL"):
            if env_key in clean:
                os.environ[env_key] = clean[env_key]
        return self.snapshot()
