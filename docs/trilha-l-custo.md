# Trilha L — Modelo de custo do fleet (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/L-modelo-de-custo.md`](https://github.com/CenturyBoys/roboto/blob/main/research/L-modelo-de-custo.md).
> **Princípio-âncora:** *não dá pra otimizar o que não se mede.* Teto mensal-alvo + alerta em 80%,
> barato-primeiro (D6). **Status:** medição real + orçamento do mês vs teto no `main`.

## 1. O que a trilha entrega

O custo do fleet **orçado e medido** — gasto por chamada/execução/mês contra um **teto mensal**, pra
a economia de token ser comprovável e o gasto previsível.

## 2. Onde o custo já é medido (base)

| Unidade | Como |
|---|---|
| por chamada | `llm_call` (tokens_in/out + `cost_usd` + `at` + tier + modelo) — trilha F |
| por execução | `cost_for_execution(run_id)` → mostrado no detalhe da execução |
| por mês | `spend_since(tenant, início-do-mês)` → agregação SQL (`SUM(cost_usd)`) |

## 3. Orçamento do mês vs teto (novo)

- **Teto:** `ROBOTO_BUDGET_USD` (config, D6: ~1 Max ≈ R$550 → ~US$100/mês). `0` = sem teto.
- **Avaliação determinística** (`app/budget.assess`): `spent / cap` → `pct`, `alert` (≥80%), `over`
  (≥100%). Pura e testada.
- **Superfície:** o endpoint `/costs` devolve o bloco `budget`; o cockpit (view **Custos**) mostra uma
  **barra de orçamento do mês** no topo — 🟢 <80% · 🟡 ≥80% · 🔴 ≥100% (`data-testid=budget-bar`).

```mermaid
flowchart LR
  LC[("llm_call<br/>cost_usd + at")] -->|spend_since(mês)| S["gasto do mês"]
  CFG["ROBOTO_BUDGET_USD<br/>(teto)"] --> A{"assess<br/>spent / cap"}
  S --> A
  A -->|< 80%| G([🟢 dentro])
  A -->|≥ 80%| Y([🟡 atenção])
  A -->|≥ 100%| R([🔴 acima])
```

## 4. Conservador (não bloqueante)

Hoje o orçamento **só surfa** o nível (mesma régua do jev-guard, trilha H): chama atenção, não corta
trabalho no meio. A **política ao estourar** (degradar o tier do modelo → pausar → escalar ao humano)
fica como follow-up, pra não cortar sem a régua calibrada.

As alavancas de redução já vivem em outras trilhas e aqui viram **orçamento mensurável**: right-sizing
(I), ferramenta certa / menos token (F), checks determinísticos fora do LLM (D/H).

## 5. Cap de `max_tokens` — reserva upfront (evita 402)

A OpenRouter **reserva** o custo MÁXIMO de cada chamada antes de rodar (`input + max_tokens × preço`).
Num request grande (ex.: Sonnet com muito contexto) a reserva pode estourar o saldo e dar **402
"would exceed your available credit"** mesmo com crédito positivo. `ROBOTO_MAX_TOKENS` capa a saída no
gateway (`OpenRouterGateway`) → reserva menor. No motor (via ccr), o mesmo cap vai pelo transformer
`maxtoken` do ccr. Complementa o **retry transitório** (trilha B): 402 também re-enfileira e retoma.

## 6. Fonte da verdade e follow-ups

O custo vive em `llm_call` (medição real, não estimativa). A view Custos mostra total, por execução e
por chamada (modelo+tier) + a barra do mês.

**Follow-ups (backlog):** teto/budget **por tipo de agente** e **por issue** (baseline medido no golden
set, trilha H); política ao estourar (degradar→pausar→escalar); latência por etapa; câmbio BRL→USD
configurável.
