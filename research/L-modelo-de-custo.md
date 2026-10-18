# Trilha L — Modelo de custo do fleet

> Status: RASCUNHO PARA REVISÃO (criada na remediação da auditoria rodada-01, 2026-10-18)

## Por que existe

A auditoria rodada-01 apontou o maior buraco: o objetivo-mãe é **economia de token**, mas
**nenhuma trilha orçava o custo agregado** do fleet. Sem modelo de custo, "economia de token" não é
verificável e o review multi-agente (Trilha D) — que **não batcheia** como o CI (Trilha J) — pode
dominar a conta sem ninguém perceber. *Não dá para otimizar o que não se mede.*

## Pergunta

Como **orçar e medir** o custo (token/$) do fleet por **agente**, por **etapa**, por **issue** e por
**PR**, com teto e alerta — de forma que a economia seja comprovável e o gasto, previsível?

## Unidades de custo

- **Por issue (custo até `done`)**: refino + planejamento + implementação + review + correções.
  É a métrica de negócio ("quanto custa fechar uma issue").
- **Por PR**: dominado pelo **review** (D) — multi-dimensão × multi-pass, re-disparado a cada
  `synchronize`. Maior risco de custo não-batcheado.
- **Por agente/etapa**: atribuição por tipo (refine/plan/impl/review/security/docs) e por modelo.

## Alavancas de redução (já decididas nas outras trilhas — aqui viram orçamento)

| Alavanca | Trilha | Efeito |
|----------|--------|--------|
| Escada de validação (determinístico → Jev → frontier) | I | evita frontier no que não precisa |
| Progressive disclosure + subagents com síntese | C, F | contexto enxuto, não paga 20 skills upfront |
| Ferramenta certa (grafo/semântica vs grep-and-read) | F | ordens de magnitude de token |
| CI batching + test impact analysis | J | -50–70% da conta de CI |
| Checks determinísticos fora do LLM (review/evals) | D, H | não gasta token no óbvio |

## Política de orçamento (proposta)

- **Teto por tipo de agente** (token/$ por run) + **budget por issue**; ao exceder, **degrada o
  tier de modelo** ou **pausa e escala ao humano** (não estoura silenciosamente).
- **Review budgetado**: teto de dimensões × passagens por PR; só roda review completo **depois** do
  gate determinístico passar (Trilha D).
- **Alerta de runaway** (loop de agente) via observabilidade (Trilha H).
- **Atribuição de custo** por feature/modelo/agente → mede o ganho real da ferramentificação (F) e
  do right-sizing (I) contra um **baseline**.

## Base de orçamento (decidida pelo dono, 2026-10-18)

A **unidade de orçamento** do fleet é **1 assinatura Max ≈ R$ 550/mês** (~US$100 na ordem de
grandeza → tier **Max 5x**; se for o Max 20x/US$200, dobrar os números), autorizada pelo CTO.

> ⚠️ **Dois modelos de cobrança distintos — isso é decisão de arquitetura, não detalhe:**
> - **Assinatura Max** = valor fixo mensal com **rate limits** (janelas de ~5h + teto semanal),
>   pensada para uso **interativo** (Claude Code / claude.ai). Não é um pool de "X tokens/mês"
>   alocável; um fleet headless sempre-ligado esbarra nos limites e na finalidade de uso.
> - **API / pay-per-token** = o que OpenRouter + Jev (Trilhas B/I/K) de fato usam; custo por token.
>
> **DECIDIDO (dono, 2026-10-18): opção (a) — API pay-per-token via OpenRouter.** A Max (~R$550/mês)
> vira o **teto mensal-alvo em $/token**, não uma assinatura rodando o fleet → os rate limits do plano
> Max **não se aplicam** ao fleet; o orçamento é puramente o valor em dólar gasto na API.
> Pool multi-provedor via OpenRouter, **incluindo modelos chineses** baratos para geração (Trilha I).

### Referência de preço de API (verificado — claude-api, cache 2026-06-04)
| Modelo | Input $/MTok | Output $/MTok |
|--------|--------------|---------------|
| Opus 4.8 | 5 | 25 |
| Sonnet 4.6 | 3 | 15 |
| Haiku 4.5 | 1 | 5 |
| **Jev** (judge, Trilha I) | ~0,042 | **grátis** |

Ordem de grandeza do que ~US$100/mês compra (ilustrativo; blend real varia): Opus ≈ 20M in / 4M out ·
Sonnet ≈ 33M in / 6,7M out · Haiku ≈ 100M in / 20M out · Jev praticamente desprezível. → o
right-sizing (Trilha I) + Jev na validação são o que fazem esse orçamento render.

## Perguntas em aberto (precisam do dono)
- [ ] Mix de provedores no OpenRouter por etapa (quais modelos chineses/abertos para geração, quando
      escalar a Claude frontier) e política de fallback entre provedores.
- [ ] Dado o teto mensal (1 Max seat), **ratear em teto por tipo de agente** e **budget-alvo por issue**.
- [ ] Custo/issue aceitável antes de acionar gate humano de custo.
- [ ] Política ao estourar: degradar modelo, pausar, ou escalar? (default sugerido: degradar → pausar → escalar).
- [ ] Plataforma de medição (liga com a decisão de observabilidade da Trilha H).

---

### Fontes
- Deriva das Trilhas [F], [I], [J], [H] e [D]; evidências quantitativas lá (todas verificadas na auditoria rodada-01).
- [Context Engineering: Why More Tokens Makes Agents Worse — Morph](https://www.morphllm.com/context-engineering)
