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
| co-piloto (conversa no cockpit) | `ROBOTO_COPILOT_MODEL` (ex.: `openrouter,qwen/qwen3.8-27b`) |

O **co-piloto** (a conversa ao vivo no cockpit — tmux via CLI ou SDK) tinha um default fraco demais
para navegar e editar o repo. `ROBOTO_COPILOT_MODEL` fixa um modelo mais forte nos dois caminhos
(`tmux_copilot` injeta `--model` no CLI; `copilot.drive_session` usa como default). Vazio = default
antigo (compat).

## 5. Observabilidade (onde o operador vê o roteamento)

A view **Custos** do cockpit mostra, por chamada, **modelo + tier + tokens + US$** (`llm_call`,
trilha F) — então o roteamento é **auditável**: dá pra ver qual modelo rodou em cada tier e o custo.

## 6. Fonte da verdade e follow-ups

O mapa tier→modelo vive em `llm/routing` (baseline) + config (overrides). O gateway é a interface;
OpenRouter é **uma** implementação (a arquitetura fala com a interface, não com o provedor).

**Follow-ups (backlog):** Jev/System One como juiz estruturado plugável (hoje: Qwen no JUDGE);
RouteLLM pra espremer o tier frontier; roteamento por **sensibilidade de dado** (self-host pra
projetos privados); re-pinagem periódica contra o golden set (trilha H).

## 7. Switcher de modelo por etapa (hot-reload, sem restart)

O operador troca o modelo de **cada etapa** pela aba **Modelos** do cockpit, **ao vivo** — sem
derrubar runs. A fonte da verdade segue o `app_config` (trilha O): a troca **persiste** lá e é
**aplicada em memória** na hora.

- **`app/live_models.py` (`LiveModels`):** `snapshot()` (estado por etapa p/ a UI) + `set_models()`
  (persiste + aplica). Rebuilda o roteamento do gateway (`OpenRouterGateway.set_routing`), troca o
  modelo dos motores (`ClaudeCodeEngine.set_model`) e atualiza o env (STRONG é lido por chamada).
- **Etapas expostas:** cheap (breakdown/chat), judge (review), frontier, refine, impl, strong/resgate
  e jev. **JEV** é a exceção: o decisor é construído 1x no boot, então a troca só vale no **próximo
  restart** (selo `restart` na UI; as demais mostram `ao vivo`).
- **API:** `GET /models` (estado) e `PUT /models` (troca) no console (bearer). `runtime` constrói o
  `LiveModels` e registra os motores quando nascem.
- **Formato do valor:** tiers do gateway usam o slug puro (`qwen/qwen3.8-flash`); refino/impl/strong
  passam pelo **ccr** e usam a sintaxe de override `openrouter,<slug>`.

## 8. Guard de sessão: resume só sob config compatível (#266)

Trocar o modelo por etapa (§7) e o **escalonamento** (#242, correção no modelo forte) criam um risco:
**retomar uma sessão nativa criada sob outro modelo** — o contexto/cache do modelo base não vale pro
forte. O guard previne isso guardando um **hash da config** (modelo + tools) na sessão e só retomando
quando ele bate. Derivado do `sessionConfig`-hash do Tucano (Apache-2.0; `research/tucano-reuso.md`).

| Peça | O que faz | Onde |
|---|---|---|
| session_config_hash | hash estável da config que torna a sessão retomável (mesma config → mesmo hash) | `app/session_guard` |
| may_resume / resumable_native_id | só retoma sob hash igual; senão começa sessão nova | `app/session_guard` |
| persistência | `session.config_hash` (migration `0013`); gravado em `create_session` | `orchestrator/*`, `migrations/0013` |
| wiring | no `_engine_turn` (pr_cycle): config mudou → **não** passa `resume` + avisa no feed (`♻️`) | `app/pr_cycle` |

- **Puro e testável** (`tests/test_session_guard`): hash estável/muda com modelo-tools-extra;
  `resumable_native_id` escolhe a sessão compatível mais recente, `None` se nenhuma bate.
- **Conservador:** sem hash guardado → não retoma (começa limpo); nunca retoma "no escuro".
