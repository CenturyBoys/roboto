# Trilha G — Memória, continuidade e second brain

> Status: ESQUELETO (pesquisa não iniciada)

## Pergunta

Como manter continuidade entre sessões/agentes **sem sessões gigantes de contexto**, e qual
camada de memória adotar?

## Princípio aplicado (determinismo primeiro)

Default de memória = **determinística, versionada e greppável**: a própria **issue + comentários
+ repo + arquivos de memória em texto**. Memória opaca (vetorial/embeddings) é o oposto de
determinismo — entra apenas como **exceção justificada**, se provarmos que texto+repo não basta.

## A pesquisar

- [ ] Padrões de handoff entre sessões/agentes (resumo durável, estado na issue).
- [ ] Ferramentas de "second brain" / memória para LLM — mapear e avaliar:
      `mem0`, `Letta`/MemGPT, `Zep`, `Basic Memory` (MCP), Obsidian+MCP, knowledge graphs, RAG/vetorial.
- [ ] Critério de corte: quando texto+repo é suficiente vs. quando uma camada externa se justifica
      (e, se sim, qual a mais auditável/determinística).
- [ ] Como a issue funciona como memória externa canônica do trabalho (amarra com Trilha A).
- [ ] Custo em token de cada abordagem de memória.

## Saída esperada

Política de memória do fleet (default texto/repo + critério de exceção para camada externa) e,
se aplicável, a ferramenta de second brain escolhida com justificativa.
