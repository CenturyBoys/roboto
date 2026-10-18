# Trilha I — Roteamento de modelos (right-sizing)

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)
>
> ✅ **Decidido** (ver `DECISOES-A-FECHAR.md`): substrato **OpenRouter**; mix inicial = 1 modelo
> chinês/aberto barato + **Claude frontier** + **Jev**; **pinar por medição** (D16).

## Pergunta

Qual é o **compute mais barato que resolve com qualidade suficiente** para cada operação? Como
roteamos, e por qual substrato?

## A escada de validação (do mais barato ao mais caro)

1. **Check determinístico — sem LLM.** Teste/lint/type-check/build/schema. Se vira script, vira
   script (= ferramentificação, Trilha F). Zero token.
2. **Decisão estruturada barata — Jev / System One (TypeSafe).** Para o que não vira código:
   "o PR cumpre o DoD?", gate de prontidão (Trilha A), scoring de review (Trilha D). Saída type-safe
   (0% erro de estrutura **por construção** — garante o *formato*, não a correção do *julgamento*) +
   **confiança calibrada**. Input ~$0.042/M, output grátis.
   > O **degrau 2 é uma interface** (classificador estruturado com confiança calibrada); **Jev é uma
   > implementação plugável**, com um judge frontier barato como fallback testado — não casar a
   > arquitetura com um produto único.
3. **Geração tiered via OpenRouter.** Modelos **abertos/baratos — incluindo provedores chineses
   (DeepSeek, Qwen/Qwen-Coder, GLM/Zhipu, Kimi/Moonshot)** — para o grosso da geração (fortes em
   coding, custo baixo); **Claude (Haiku → Sonnet → Opus)** reservado para o raciocínio mais difícil
   e etapas sensíveis a qualidade. Right-size por etapa (refinar vs arquitetar vs implementar vs revisar).

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

> **DECIDIDO (dono, 2026-10-18): OpenRouter é o substrato** (opção API pay-per-token, Trilha L).
> Um endpoint + billing único + acesso a **provedores chineses** (DeepSeek, Qwen, GLM/Zhipu, Kimi):
> fortes em coding e muito baratos → ideais para os tiers de geração, reforçando a economia de token.

> **Contingência (resolve finding rodada-02)**: OpenRouter concentra 4 funções (billing + roteamento +
> acesso ao Jev + egress) → ponto único. Mitigar: falar com uma **interface de gateway** (OpenRouter =
> **uma** implementação), com **fallback** para APIs diretas dos provedores / LiteLLM self-host, e Jev
> também acessível pela **API direta da TypeSafe**. O "desacoplar de um vendor" (rodada-01) vale para o
> OpenRouter também — a arquitetura fala com a interface, não com o provedor.

**Evidência (fonte primária LMSYS, arXiv 2406.18665, verificada)**: no MT-Bench, RouteLLM atinge
**95% da qualidade do GPT-4 roteando só 26% das queries** ao modelo forte (~3,66× de economia; até
-85% de custo). Em MMLU/GSM8K o ganho é menor (1,41×/1,49×, a 92%/87% de qualidade). Vale para o tier 3.

## Como a confiança calibrada vira gate
O score do Jev define um **threshold de escalonamento**: abaixo do limiar → escala para modelo
maior ou para humano. Conecta com os gates da Trilha H e o gate de prontidão da Trilha A.

## Mapa modelo → tarefa (por benchmark)

> ⚠️ **Disciplina de fontes.** Leaderboards públicos de 2026 trazem números conflitantes e até
> modelos de nomes "futuros"/não verificáveis. O que vale aqui é **o conjunto de benchmarks por tipo
> de tarefa** + **candidatos por tier**; os números são **indicativos**, a confirmar no nosso golden
> set (Trilha H) antes de pinar qualquer modelo. Para Claude, a fonte autoritativa é a skill
> `claude-api` (Opus 4.8 / Sonnet 4.6 / Haiku 4.5 / Fable 5) — ignorar alegações de "Opus 5" etc. até verificar.

### Benchmark por tipo de tarefa
| Tarefa (agente) | Benchmarks de referência |
|-----------------|--------------------------|
| Implementação / coding | **SWE-bench Verified**, **SWE-bench Pro**, LiveCodeBench, Aider polyglot, Terminal-Bench |
| Agêntico long-horizon | SWE-bench Pro, Terminal-Bench, RoadmapBench / DeepSWE |
| Planejamento / raciocínio | ARC-AGI-2, GPQA, suites de reasoning |
| Review / bug-finding | CodeJudgeBench (LLM-as-judge) + estudos de FP da Trilha D (QASecClaw, Sifting the Noise) |
| Refinamento / clarificação | ClarifyCodeBench, Ambig-SWE (Trilha A), IFEval-style |
| Guardrail / classificação | não é benchmark gerativo → acurácia + confiança calibrada no **nosso** golden set (Jev) |

### Candidatos por tier (indicativo, a validar)
| Tier | Candidatos | Nota |
|------|------------|------|
| Geração barata (OpenRouter, chineses/abertos) | DeepSeek (V3.x+), Qwen3-Coder, GLM (4.6/4.7), Kimi | fortes em coding; flash tiers ~$0,15–0,60/MTok → workhorse de implementação/testes |
| Frontier (Claude via OpenRouter) | Opus 4.8 (hardest), Sonnet 4.6 (balance), Haiku 4.5 (barato) | raciocínio difícil, arquitetura, review sensível |
| Judge / guardrail | Jev / System One | DoD, gate de prontidão, scoring de review (deny/ask/allow) |

Relato de mercado (indicativo): modelos chineses abertos entregam SWE-bench competitivo a custo de
saída muito menor — é o que justifica reservar Claude só para o topo.

### Como validamos (não pinar por leaderboard)
1. Montar um **golden set por tipo de tarefa** (Trilha H) a partir de issues/PRs reais.
2. Rodar os candidatos de cada tier nesse set; medir **qualidade E custo/latência** (Trilha L).
3. Pinar o **modelo mais barato que passa o limiar de qualidade** da etapa (right-sizing).
4. **Re-rodar periodicamente** — o ranking vira rápido; o mapa é **vivo**, não fixo.

## Riscos
- **Jev é vendor novo e vira dependência transversal (A/D/H/I)** → **isolar atrás de uma interface/
  adapter trocável**, manter fallback (judge frontier barato) e **validar nos nossos casos antes de
  confiar**. "Não alucina (por construção)" e "CTO autorizou" **não são evidência técnica** de que
  resolve os nossos casos — são premissas a testar (eval, Trilha H).
- **OpenRouter/terceiros + código privado**: enviar código a terceiros tem risco de privacidade.
  `roboto` é público, mas projetos futuros podem ser privados → avaliar roteamento self-host nesses casos.
- **Provedores chineses + dados sensíveis/jurisdição — política vale JÁ, não só "futuro"** (resolve
  finding rodada-02): como são **workhorse de geração desde o início**, definir **roteamento por
  sensibilidade de dado agora** — classificar cada task (pública / interna / sensível) e restringir
  dados sensíveis a tiers confiáveis ou self-host, mesmo com o `roboto` atual sendo público. Avaliar
  residência de dados e retenção por provedor.
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
- [SWE-bench Verified Leaderboard & Methodology — vals.ai](https://www.vals.ai/benchmarks/swebench) *(indicativo)*
- [The Open Weight Models that Matter, June 2026 — OpenRouter](https://openrouter.ai/blog/insights/the-open-weight-models-that-matter-june-2026/) *(indicativo)*
- [Best Chinese LLMs 2026: DeepSeek, Qwen, GLM, Kimi — YottaLabs](https://www.yottalabs.ai/post/best-chinese-llm-models-2026-deepseek-qwen-glm-kimi-compared) *(indicativo)*
- [CodeJudgeBench: Benchmarking LLM-as-a-Judge for Coding Tasks (arXiv 2507.10535)](https://arxiv.org/abs/2507.10535)
