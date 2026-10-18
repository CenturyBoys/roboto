# Trilha G — Memória, continuidade e second brain

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Como manter continuidade entre sessões/agentes **sem sessões gigantes**, e qual camada de memória adotar?

## Princípio aplicado (determinismo primeiro) — e a pesquisa concorda

Default = memória **determinística, versionada e greppável**: issue + repo + arquivos `.md`.
A pesquisa de 2026 confirma um **shift "file-first"**: Manus, OpenClaw e o próprio Claude Code
usam Markdown como primitiva central de memória, **não** um vector DB como fonte da verdade.
Auditabilidade: markdown = alta (legível, versionável); vector DB = moderada (precisa de tooling).

## O insight-chave: separar STORAGE de SEARCH

- **Storage = fonte da verdade** → arquivos `.md` + git (determinístico, auditável, com rollback nativo).
- **Search = cache derivado** → índice local (SQLite **FTS5/BM25**, opcionalmente + vetor) que
  **sempre pode ser reconstruído a partir dos arquivos**. Se o índice some, rebuilda; os arquivos mandam.
- Padrão HERMES: memória pequena e bounded em Markdown, recall determinístico via FTS5 (BM25),
  **sem chamadas de LLM para recuperar**. (= recuperação barata e determinística.)

> Ou seja, não é "markdown OU vetor": é markdown como verdade + um índice derivado (que pode ser
> semântico) para busca. Isso casa com a regra de roteamento de busca da Trilha F.

## Landscape de frameworks externos (usar só como exceção)

| Framework | Arquitetura | Força | Nota |
|-----------|-------------|-------|------|
| **Mem0** | híbrido vetor+grafo+KV, extração passiva | personalização; ~48K stars | LongMemEval 49,0% |
| **Zep/Graphiti** | knowledge graph **temporal** (fatos com janela de validade) | raciocínio temporal; **melhor acurácia** | LongMemEval 63,8% |
| **Letta** (MemGPT) | runtime onde o LLM gerencia a própria memória via tools | long-running | OS-inspired |
| **LangMem** | — | stacks LangChain | — |

Critério de adoção: só escalar para um desses se **raciocínio temporal** ou **escala cross-session**
provar que arquivos+índice derivado não bastam. Se precisar, **Zep** lidera em acurácia.

## Específico de agente de código

Codebase já é um estado grande, estruturado, versionado, **com rollback** — a memória precisa
**respeitar o git**. Coerência cross-session exige guardar: convenções do projeto, fixes anteriores,
estrutura do código. No nosso fleet isso mora em: **issue** (estado/trabalho, Trilha A), **repo**
(código/ADRs/AGENTS.md), **`.md` de memória** (fatos/decisões).

## Recomendação

1. **Fonte da verdade**: issue + repo + `.md`. Nada de vector DB como primário.
2. **Busca**: índice derivado rebuildável (FTS5/BM25) para recall determinístico barato; semântico
   opcional por cima.
3. **Framework externo** (Zep/Mem0/Letta): **exceção justificada**, medida contra o default
   (VibeMemBench avalia memória em tasks reais de repo — insumo de evals, Trilha H).

## Perguntas em aberto
- [ ] Já montamos o índice derivado (FTS5) no MVP, ou issue+repo bastam no começo?
- [ ] Formato canônico dos `.md` de memória do fleet (fatos, decisões, handoff) e onde vivem no `roboto`.
- [ ] Gatilho de "exceção" para framework externo: qual métrica/limite dispara a avaliação?

---

### Fontes
- [The Markdown Memory Paradigm in AI Agent Architectures — Substack](https://micheallanham.substack.com/p/the-markdown-memory-paradigm-in-ai)
- [The Markdown File That Beat a $50M Vector Database (storage vs search) — dev.to](https://dev.to/codingsimba/the-markdown-file-that-beat-a-50m-vector-database-separating-storage-and-search-in-agent-memory-3d14)
- [memweave: Zero-Infra Memory with Markdown + SQLite — Towards Data Science](https://towardsdatascience.com/memweave-zero-infra-ai-agent-memory-with-markdown-and-sqlite-no-vector-database-required/)
- [Best AI Agent Memory Frameworks 2026 (Mem0/Zep/Letta) — Atlan](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)
- [VibeMemBench: Evaluating Memory Systems for Coding Agents (arXiv)](https://arxiv.org/pdf/2609.23570)
- [Memory as Infrastructure: Persistent Agent Memory in Months-Long Development (arXiv)](https://arxiv.org/pdf/2609.05510)
