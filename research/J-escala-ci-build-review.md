# Trilha J — Escala: build/CI, carga de testes e de revisores

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Com o fleet em volume, muitos PRs/builds/pipelines disputam recursos. Que **políticas de
escalonamento** evitam fila infinita, desperdício de CI e sobrecarga de revisores?

> Quase tudo aqui é **política determinística** (princípio-mãe), não decisão de LLM.

## 1. Prioridade e fila de build/CI
- **Prioridade** por issue/épico (fila com prioridade).
- **Cancelar builds superados**: `concurrency groups` / cancel-in-progress ao chegar commit novo.
- **Merge queue** (GitHub Merge Queue 2026): **batch de N PRs usa 1 run de CI** → custo por PR
  mergeado cai ~N-vezes; testa o estado real pós-merge. Monorepo é quem mais ganha (mudança em lib
  compartilhada quebra downstream).
- **Build só do afetado**: path filters + grafo (Nx/Turborepo/Bazel) + cache; reduzir matrix.

## 2. Carga de testes
- **Test impact analysis / seleção de testes afetados** (Nx, Turborepo, Bazel; AST via ts-morph em
  TS) em vez de rodar tudo. **Economia típica 50–70% da conta de CI**; horas → minutos.
- **Suites em camadas**: smoke/rápido no PR, suite completa no merge/noturno (two-step CI).
- **Flaky é crítico com merge queue**: um teste que falha 5% numa PR passa a ter 5% de derrubar a
  fila inteira a cada ciclo → **quarentena de flaky** + retry controlado (Trunk.io).

## 3. Carga de revisores (humanos e agentes)
- **Batch de itens similares**, **route por expertise**, e **pausar trabalho de baixo valor quando
  a carga de review sobe**.
- Rastrear **disponibilidade de revisor** (PRs esperando pessoa específica vs. qualquer um);
  rotação / ampliar o pool.
- Dedup de revisão entre PRs sobrepostos; respeitar rate limits (API de LLM e GitHub).

## 4. Backpressure / WIP limits
- **Sem backpressure, a fila converte todo impulso upstream em movimento downstream** — agentes
  começam tarefas sobrepostas enquanto saídas anteriores seguem sem review/merge, gerando pilhas
  de review grandes demais.
- **WIP limit**: cap de delegados concorrentes; ao atingir, o orquestrador **enfileira** novos
  dispatches até abrir vaga.
- **Dispatch gating**: ondas posteriores dependem de resultados parciais das anteriores (refina o
  despacho). Amarra com a orquestração (Trilha B).

## 5. Grafo de dependências e prevenção de colisão de código (crítico)
Issue/épico que **depende de** (é bloqueada por) outra **não pode ser desenvolvida em paralelo** —
senão dois agentes mexem na mesma área e o código "se cruza".
- **Relações de bloqueio explícitas**: "blocked by / blocking" nativo do GitHub (ou labels) na DoR
  (Trilha A). Issue em `blocked` **não entra em execução**.
- **Ignorar dependências de PR engana o diagnóstico de gargalo** (o atraso vem de PR bloqueado/draft,
  não do review).
- **Scheduling ciente de dependência**: não iniciar antes de a bloqueadora mergear; serializa o que colide.
- **Previsão de sobreposição**: usar os "arquivos/área prováveis" da DoR para detectar issues que
  tocam o mesmo código e **não paralelizá-las** (ou isolar via worktree/container, Trilha K).
- **Conflito de merge = gate humano**: resolução revisada e aprovada por humano; o agente NÃO
  auto-resolve conflito sem aprovação (Trilha H).

## Recomendação
Merge queue com batching + test impact analysis (two-step CI) + quarentena de flaky como base
determinística; WIP limit + backpressure no orquestrador; scheduling ciente de dependência com
`blocked by`; conflito sempre para gate humano.

## Perguntas em aberto
- [ ] Stack do `roboto` define a ferramenta de impacto (Nx/Turborepo/Bazel/ts-morph)? (amarra Trilha E/K)
- [ ] Valor inicial de WIP limit e critério de prioridade de build.
- [ ] Política de quarentena de flaky (quantas falhas → quarentena).

---

### Fontes
- [Monorepo CI: Running Only the Tests That Matter — Mergify](https://mergify.com/learn/monorepo/ci)
- [Scale CI for Agent PRs: Test Slicing & Impact Analysis in Actions — SitePoint](https://www.sitepoint.com/optimize-github-actions-agent-prs-test-slicing/)
- [GitHub Merge Queue in 2026: How It Works & Flaky Checks — tenki.cloud](https://tenki.cloud/blog/github-merge-queue-setup)
- [Merge Queues for Large Monorepos — Aviator](https://www.aviator.co/blog/merge-queues-for-large-monorepos/)
- [Stop flaky tests from sabotaging your merge queue — Trunk.io](https://trunk.io/blog/stop-flaky-tests-from-sabotaging-your-merge-queue)
- [Agent Queues Need Backpressure — Everett Quebral](https://www.everettquebral.com/blog/artificial-intelligence/agent-queues-need-backpressure)
- [How to Unblock Your AI PR Review Bottleneck — freeCodeCamp](https://www.freecodecamp.org/news/how-to-unblock-ai-pr-review-bottleneck-handbook/)
