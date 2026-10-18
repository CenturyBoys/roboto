# Trilha J — Escala: build/CI, carga de testes e de revisores

> Status: ESQUELETO (pesquisa não iniciada)

## Pergunta

Quando o fleet roda em volume, muitos PRs, builds e pipelines de CI/CD são disparados ao mesmo
tempo e disputam recursos. Que **políticas de escalonamento** evitam fila infinita, desperdício
de minutos de CI e sobrecarga de revisores (humanos ou agentes)?

Observação: quase tudo aqui é **política determinística** (princípio-mãe "determinismo primeiro")
— regra de scheduling, não decisão de LLM.

## Sub-áreas

### 1. Prioridade e fila de build/CI
- [ ] Priorização por prioridade da issue/épico (fila com prioridade).
- [ ] **Cancelar builds superados**: concurrency groups / cancel-in-progress quando chega commit novo.
- [ ] **Merge queue** (GitHub merge queue) para serializar merges e testar o estado real pós-merge.
- [ ] Batching de mudanças compatíveis.
- [ ] Controle de custo: path filters, build só do que foi afetado (grafo/monorepo), cache, reduzir matrix.

### 2. Carga de testes
- [ ] **Test impact analysis / seleção de testes afetados** em vez de rodar tudo sempre.
- [ ] **Suites em camadas**: smoke/rápido no PR, suite completa no merge/noturno.
- [ ] Sharding/paralelização; cache de resultados.
- [ ] Tratamento de testes flaky (quarentena, retry controlado).

### 3. Carga de revisores (humanos e agentes)
- [ ] Distribuição/atribuição de revisão entre agentes revisores; evitar sobrecarregar um só.
- [ ] Dedup de revisão entre PRs sobrepostos.
- [ ] Rate limits (API de LLM e GitHub) e backpressure.

### 4. Backpressure / WIP limits
- [ ] Quando a pipeline satura, agentes **reduzem o ritmo** de abrir PRs (limites de work-in-progress).
- [ ] Amarra com o grafo de dependências entre issues (Trilha A) e com a orquestração (Trilha B).

### 5. Grafo de dependências e prevenção de colisão de código (crítico)
Uma issue/épico que **depende de** (é bloqueada por) outra **não pode ser desenvolvida em
paralelo** — senão dois agentes mexem na mesma área e o código "se cruza".
- [ ] **Relações de bloqueio explícitas**: usar "blocked by / blocking" nativo do GitHub (ou
      labels) na DoR (Trilha A). Issue em `blocked` **não entra em execução**.
- [ ] **Scheduling ciente de dependência**: não iniciar uma issue antes de a bloqueadora estar
      merjada. Serializa o que colide.
- [ ] **Previsão de sobreposição**: usar os "arquivos/área prováveis" da DoR para detectar issues
      que tocam o mesmo código e **evitar paralelizá-las** (ou isolar via worktree/container, Trilha K).
- [ ] **Resolução de conflito = gate humano**: quando houver conflito de merge, a resolução deve
      ser **revisada e aprovada por humano** — o agente NÃO auto-resolve conflito sem aprovação.
      (Amarra com os gates humanos da Trilha H.)

## Saída esperada

Política de escalonamento (prioridade de build + estratégia de testes em camadas + distribuição
de revisão + WIP/backpressure), majoritariamente determinística, que entra na orquestração
(Trilha B) e vira regra operacional.
