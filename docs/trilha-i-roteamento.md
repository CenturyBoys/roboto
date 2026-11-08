# Trilha I — Roteamento de modelos (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/I-roteamento-de-modelos.md`](https://github.com/CenturyBoys/roboto/blob/main/research/I-roteamento-de-modelos.md).
> **Princípio-âncora:** o **compute mais barato que resolve com qualidade suficiente** por etapa
> (right-sizing). Substrato = **OpenRouter** (um endpoint, billing único, provedores baratos).
> **Status:** escada de validação + tier→modelo por config + **fallback** no `main`.

## 1. A escada de validação (do barato ao caro)

1. **Check determinístico — sem LLM** (lint/type/test, DoR estrutural, risk-tiering, secret-scan).
   Zero token — ver trilhas A/F/H.
2. **Juiz barato estruturado** (`Tier.JUDGE`): DoD, prontidão (DoR semântico), scoring de review.
3. **Geração tiered** (`Tier.CHEAP` / `Tier.FRONTIER`): o grosso da geração em modelo barato; o
   raciocínio difícil no forte.

## 2. Classificação de tier (determinística + Jev degrau-2)

`app/tiering.classificar_tier` decide **forte vs barato** sem LLM (degrau-1), por sinais do texto:

| Sinal | → |
|---|---|
| ≥ `ROBOTO_TIER_FILES` (6) arquivos citados **ou** keyword de arquitetura (ADR/refactor/migração/breaking) + corpo longo | **forte** |
| resto | **barato** |

Alimenta o right-sizing da implementação (`pr_cycle`) — tarefa grande/arquitetural sobe pro modelo forte.

**Degrau-2 (Jev), `app/tiering.precisa_forte`** — espelha `web_research.research_is_critical`: o
degrau-1 decide primeiro; se já mandou pro **forte**, respeita (não rebaixa, nem consulta o Jev — o
keyword é sinal forte). Se disse **base**, o `Decider` (Jev) pode **promover** uma issue de escopo
amplo que o keyword não pegou (`decision && confidence ≥ limiar`). Jev falhou → cai no
determinístico. Nunca bloqueia (determinismo 1º). O `runtime` passa o `refine_decider` já existente;
sem decider = só determinístico.

**Finalização no forte (`ROBOTO_FORTE_FINALIZE`, proativo, #242)** — o **base** escreve o rascunho
(1º turno) e o **forte** fecha a parte chata (diag / hook / correção / secret-fix). Default `0` =
**reativo** (só escala quando trava, via degrau de escalonamento). A/B contra o reativo.

## 3. Tier → modelo, por config + fallback (novo)

O gateway resolve cada tier para uma **cadeia** de modelos (`llm/routing.build_routing`): o primário
e, atrás, o **baseline conhecido-bom** como fallback.

| Tier | Override (env) | Default (baseline) |
|---|---|---|
| `CHEAP` | `CHEAP_MODEL` | `qwen/qwen-2.5-72b-instruct` |
| `JUDGE` | `JUDGE_MODEL` | `qwen/qwen-2.5-72b-instruct` |
| `FRONTIER` | `FRONTIER_MODEL` | `qwen/qwen3-coder` |

- **Override vem com fallback:** se você pina o JUDGE num modelo de raciocínio e ele falha (provedor
  fora), o gateway cai pro baseline do **mesmo tier** — nunca pra outro tier (evita queda silenciosa
  de qualidade). `OpenRouterGateway.complete` tenta a cadeia na ordem.
- **Juiz determinístico:** `Tier.JUDGE` manda `temperature=0` (mesmo diff → mesmo veredito — trilha D).
- **Pinar por medição (D16):** os defaults são baseline; a régua final vem do golden set (trilha H) +
  custo/latência (trilha L), não de leaderboard.

## 4. Tier por operação (hoje)

| Operação | Tier |
|---|---|
| refino / chat | `CHEAP` |
| juiz semântico da issue (DoR) | `JUDGE` → escala `FRONTIER` se confiança baixa (#160) |
| review de PR | `JUDGE` (temp=0, reviewer≠autor) |
| implementação (motor Claude Code) | right-sizing via `classificar_tier` → modelo do motor (ccr) |

## 5. Observabilidade (onde o operador vê o roteamento)

A view **Custos** do cockpit mostra, por chamada, **modelo + tier + tokens + US$** (`llm_call`,
trilha F) — então o roteamento é **auditável**: dá pra ver qual modelo rodou em cada tier e o custo.

## 6. Fonte da verdade e follow-ups

O mapa tier→modelo vive em `llm/routing` (baseline) + config (overrides). O gateway é a interface;
OpenRouter é **uma** implementação (a arquitetura fala com a interface, não com o provedor).

**Follow-ups (backlog):** Jev/System One como juiz estruturado plugável (hoje: Qwen no JUDGE);
RouteLLM pra espremer o tier frontier; roteamento por **sensibilidade de dado** (self-host pra
projetos privados); re-pinagem periódica contra o golden set (trilha H).
