# Trilha D — Review de PR com agentes

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Como fazer review de PR com agentes com **sinal alto e pouco ruído** — o fator que separa uma
ferramenta útil de uma que afoga o dev em falso-positivo?

## Estado da arte (2026) — o trade-off recall × precisão

Em benchmarks de mercado, o eixo é **quantos bugs pega** vs **quanto ruído gera**:
- **Greptile** — indexa o repo num code graph; recall alto (~82% de captura de bug) mas ruidoso
  (~11 falsos-positivos por run).
- **CodeRabbit** — baixo ruído e ainda assim #1 em recall no benchmark independente da Martian
  (~300k PRs). Melhor generalista.
- **Graphite Diamond** — o **menor ruído** ("todo comentário acerta"), pega menos bug cru.

Para um **fleet** (onde o dev é também agente e o overload trava a pipeline, Trilha J), a aposta é
**viés para precisão** — cada comentário tem que valer — sem abrir mão de recall via verificação.

## O que comprovadamente aumenta o sinal

- **Multi-pass com voto/consenso**: várias passagens independentes (com ordem do diff embaralhada)
  + maioria → resolução sobe de ~52% para >70%. Uma passagem única gera FP demais.
- **Multi-agente por dimensão + verificação**: agentes especializados em paralelo (classes de
  problema distintas) sob um coordenador, seguidos de um **passo de verificação que re-lê a fonte
  antes de postar** → captura ~89% das vulnerabilidades vs 43% de passagem única, e **FP cai de
  32% para 8%**.
- **Remover checks determinísticos do escopo do LLM** (determinismo primeiro!): lint/type/test/
  build/secret-scan já são pegos pelo CI; o LLM **não** deve reflagar isso — foca em lógica/design.
- **Escopo apertado**: dizer a cada reviewer **o que NÃO flagar** e escopo por path.
- **Exigir evidência** em cada finding.
- **Input certo = token certo**: PR title+description + **diff + trechos relevantes** supera o
  "dump do repo inteiro" quase sempre (ganho de token).
- **Output estruturado por finding**: `{title, severity, file, line_range, evidence, recommendation,
  confidence}` → permite filtrar por severity/confidence e **medir taxa de aceite**.

## Desenho recomendado para o nosso agente de Review

1. **Gate determinístico primeiro** (CI): lint, type-check, build, testes, secret/SCA scan. O LLM
   nunca reflaga o que o CI já cobre.
2. **Review multi-agente por dimensão** sobre `diff + snippets`: correção/bug, segurança,
   design/simplicidade, performance, testes. (Encaixa no padrão find→verify de workflow multi-agente.)
3. **Verificação adversarial** re-lendo a fonte, com voto/consenso → mata FP antes de postar.
4. **Filtro por severity + confidence**: o scoring/gate barato pode ser o **Jev** (Trilha I);
   confiança calibrada vira threshold (abaixo → não posta ou escala).
5. **Reviewer ≠ implementador** (regra da Trilha A — quem gera não valida).
6. **Comentários inline** com evidência + recomendação; `pull_request.synchronize` re-dispara o
   loop fix→review (Trilha B).
7. **Feedback loop**: trackear accept/dismiss de cada comentário → afina prompts/thresholds
   (vira insumo de evals, Trilha H).

## Impacto em token
- `diff + snippets` em vez de repo inteiro.
- Checks determinísticos fora do LLM = menos tokens gastos no óbvio.
- Confiança calibrada evita re-rodadas desnecessárias.

## Perguntas em aberto
- [ ] Quais dimensões de review no MVP (bug + segurança + simplicidade?) e quantas passagens de voto?
- [ ] Threshold de severity/confidence para postar vs. silenciar vs. escalar ao humano.
- [ ] Usamos uma ferramenta pronta (CodeRabbit/Diamond) como baseline e medimos contra o nosso, ou
      construímos direto? (recomendo baseline para calibrar sinal/ruído).

---

### Fontes
- [Agentic Code Review: What Works in 2026 — designkey](https://www.designkey.studio/post/agentic-code-review-what-works-2026)
- [Best AI Code Review Tools 2026 (Greptile/CodeRabbit/Diamond/Qodo) — Greptile](https://www.greptile.com/content-library/best-ai-code-review-tools)
- [How to Review AI-Generated Code in 2026: Pipeline & Best Practices — CodeAnt](https://codeant.ai/blogs/how-to-review-ai-generated-code)
- [Why AI Code Review Overwhelms Developers and How to Fix It — CodeAnt](https://codeant.ai/blogs/prevent-ai-code-review-overload)
- [How Accurate Is AI Code Review? False Positives, Recall, Trust — Augment](https://www.augmentcode.com/guides/ai-code-review-accuracy)
- [Multi-Agent Code Verification via Information Theory (arXiv)](https://arxiv.org/pdf/2511.16708)
- [Autonomous Multi-Agent Code Review with CodeQL + LLM Triage — Daily AI World](https://dailyaiworld.com/workflow/build-autonomous-multi-agent-code-review-pipeline-codeql)
