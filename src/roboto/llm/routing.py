"""Política de roteamento tier → modelo (Trilha I — right-sizing).

Cada tier (CHEAP/JUDGE/FRONTIER) resolve para uma **cadeia** de modelos: o primeiro é o escolhido;
os seguintes são **fallback** (resiliência — OpenRouter concentra billing/roteamento/egress num
ponto só, então um override vem com o default conhecido-bom atrás). Pinável por medição (D16): os
defaults são o baseline; a config sobrepõe o primário sem perder o fallback.

Determinístico e sem I/O — o gateway (`OpenRouterGateway`) consome a cadeia e tenta na ordem.
"""

from __future__ import annotations

from roboto.llm.port import Tier

# baseline pinado por medição (D16): Qwen via OpenRouter. Sobreponível por config (trilha I).
DEFAULT_MODELS: dict[Tier, str] = {
    Tier.CHEAP: "qwen/qwen-2.5-72b-instruct",
    Tier.JUDGE: "qwen/qwen-2.5-72b-instruct",
    Tier.FRONTIER: "qwen/qwen3-coder",
}


def _chain(override: str, default: str) -> tuple[str, ...]:
    """Cadeia de um tier: override primeiro, default conhecido-bom como fallback. Sem override (ou
    override == default) → só o default. NÃO cai pra outro tier (evita queda silenciosa de
    qualidade); o fallback é sempre o baseline do MESMO tier."""
    o = override.strip()
    return (o, default) if o and o != default else (default,)


def build_routing(
    *, cheap: str = "", judge: str = "", frontier: str = ""
) -> dict[Tier, tuple[str, ...]]:
    """Monta as cadeias tier→modelos a partir dos overrides de config (vazio = usa o default).

    GUARD do revisor (P1a): o review roda no tier JUDGE; ele NÃO pode ser o MESMO modelo do tier
    barato (o "escritor"). Um juiz tão fraco quanto quem escreveu é cego pro próprio erro
    sistemático (run-1047: 3 rodadas de whack-a-mole no mesmo bug). Se o JUDGE primário colidir
    com o CHEAP primário (o caso DEFAULT: ambos qwen-2.5-72b), promovemos o review pro tier FRONTIER
    (mais forte). Um `judge=` explícito e DISTINTO (ex.: Sonnet) vence o guard."""
    cheap_chain = _chain(cheap, DEFAULT_MODELS[Tier.CHEAP])
    frontier_chain = _chain(frontier, DEFAULT_MODELS[Tier.FRONTIER])
    judge_chain = _chain(judge, DEFAULT_MODELS[Tier.JUDGE])
    if judge_chain[0] == cheap_chain[0]:  # revisor == escritor → promove p/ modelo mais forte
        judge_chain = frontier_chain
    return {Tier.CHEAP: cheap_chain, Tier.JUDGE: judge_chain, Tier.FRONTIER: frontier_chain}
