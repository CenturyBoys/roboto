# Trilha I — Roteamento de modelos (right-sizing)

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Qual é o **compute mais barato que resolve com qualidade suficiente** para cada operação? Como
roteamos, e por qual substrato?

## A escada de validação (do mais barato ao mais caro)

1. **Check determinístico — sem LLM.** Teste/lint/type-check/build/schema. Se vira script, vira
   script (= ferramentificação, Trilha F). Zero token.
2. **Decisão estruturada barata — Jev / System One (TypeSafe).** Para o que não vira código:
   "o PR cumpre o DoD?", gate de prontidão (Trilha A), scoring de review (Trilha D). Saída type-safe
   (0% erro de estrutura, não alucina) + **confiança calibrada**. Input ~$0.042/M, output grátis.
3. **Frontier tiered — Haiku → Sonnet → Opus.** Só quando há raciocínio/geração de verdade;
   right-size por etapa (refinar vs arquitetar vs implementar vs revisar).

## Jev / System One — detalhes de acesso (atualizado)

- Lançado 15/set/2026; decision engine: estado do programa + perguntas tipadas → respostas
  estruturadas com probabilidades calibradas, em paralelo num request.
- **Acesso (nosso caso): LIBERADO via OpenRouter, com autorização do CTO.** Ou seja, não dependemos
  da waitlist pública — rodamos o Jev através do OpenRouter (mesmo substrato de roteamento/billing).
  API direta de referência: `POST https://api.typesafe.ai/v1/systemone`, modelo `jev-latest`;
  SDKs Python (`typesafe-sdk`) e JS/TS (`@typesafe-ai/sdk`). **Ação**: avaliar nos nossos casos reais.
- **`jev-guard`**: classifica cada tool call em **deny / ask / allow**. Isso é *diretamente* a
  camada "output = proposta → política decide" da Trilha H: `deny` (least privilege), `ask`
  (gate humano), `allow`. Forte candidato a guardrail do fleet.

## Substrato de roteamento

| Opção | O que é | Uso |
|-------|---------|-----|
| **OpenRouter** | 1 endpoint, 100+ modelos, routing por preço + **fallback** out-of-the-box | substrato zero-ops, um billing |
| **RouteLLM** (LMSYS, OSS) | roteia aprendido entre modelo "forte" e "fraco" | cortar custo no tier frontier |
| LiteLLM / Bifrost / Kong AI GW | tradução de protocolo / throughput / gateway | alternativas de infra |

**Evidência (fonte primária LMSYS, arXiv 2406.18665, verificada)**: no MT-Bench, RouteLLM atinge
**95% da qualidade do GPT-4 roteando só 26% das queries** ao modelo forte (~3,66× de economia; até
-85% de custo). Em MMLU/GSM8K o ganho é menor (1,41×/1,49×, a 92%/87% de qualidade). Vale para o tier 3.

## Como a confiança calibrada vira gate
O score do Jev define um **threshold de escalonamento**: abaixo do limiar → escala para modelo
maior ou para humano. Conecta com os gates da Trilha H e o gate de prontidão da Trilha A.

## Riscos
- **Jev é vendor novo e vira dependência transversal (A/D/H/I)** → **isolar atrás de uma interface/
  adapter trocável**, manter fallback (judge frontier barato) e **validar nos nossos casos antes de
  confiar**. "Não alucina (por construção)" e "CTO autorizou" **não são evidência técnica** de que
  resolve os nossos casos — são premissas a testar (eval, Trilha H).
- **OpenRouter/terceiros + código privado**: enviar código a terceiros tem risco de privacidade.
  `roboto` é público, mas projetos futuros podem ser privados → avaliar roteamento self-host nesses casos.
- Cada vendor novo (TypeSafe, OpenRouter) é superfície operacional.

## Recomendação
Escada de validação como política padrão; **OpenRouter como substrato** (fallback/billing único);
**RouteLLM** para espremer o tier frontier; **Jev** (liberado via OpenRouter, autorizado pelo CTO) para decisões
estruturadas + **`jev-guard`** como guardrail de tool call, com fallback de judge para resiliência.

## Perguntas em aberto
- [ ] Mapa operação→tier concreto (tabela por etapa do fleet).
- [ ] Jev já liberado via OpenRouter (autorizado pelo CTO) — qual judge frontier fica de fallback?
- [ ] Self-host de roteamento para projetos privados futuros?

---

### Fontes
- [Top LLM Routing Tools in 2026: Architectures, Benchmarks, Trade-offs — dev.to](https://dev.to/artem42/top-llm-routing-tools-in-2026-architectures-benchmarks-and-production-trade-offs-ife)
- [RouteLLM: Learning to Route LLMs with Preference Data — LMSYS (fonte primária, arXiv 2406.18665)](https://arxiv.org/abs/2406.18665)
- [LLM Router 2026: RouteLLM Benchmarks, Cut Costs 30-85% — Klymentiev](https://klymentiev.com/blog/llm-router)
- [RouteLLM vs OpenRouter vs Not Diamond (2026) — nomadx](https://nomadx.ae/blog/llm-model-routing-routellm-openrouter-notdiamond-2026/)
- [TypeSafe AI Releases Jev — MarkTechPost](https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/)
- [Jev API: Pricing and Use Cases — apimaster](https://apimaster.ai/blog/jev-api)
- [How to Use Jev: practical guide (jev-guard deny/ask/allow) — dev.to](https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e)
