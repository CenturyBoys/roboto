# Trilha J — Escala: fila, WIP e colisão (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/J-escala-ci-build-review.md`](https://github.com/CenturyBoys/roboto/blob/main/research/J-escala-ci-build-review.md).
> **Princípio-âncora:** quase tudo aqui é **política determinística**, não decisão de LLM.
> **Status:** concurrency-lock por issue + **WIP limit / backpressure** no `main`.

## 1. O que a trilha entrega

Políticas de escalonamento pra o fleet não virar fila infinita nem pilha de review a jusante quando
o volume cresce — **sem** gastar decisão de LLM nisso.

## 2. Serialização por entidade (já existente)

**Concurrency-lock por (tenant, issue)** (#165): no máximo **1 run ativo por issue** — dois eventos
da mesma issue não rodam em paralelo (evita dois agentes mexendo na mesma área = código que "se
cruza"). No Pg, advisory xact lock + `NOT EXISTS` de irmão ativo; no InMemory, o `busy` set.

## 3. WIP limit / backpressure (novo)

> *Sem backpressure, a fila converte todo impulso upstream em movimento downstream* — agentes abrem
> tarefas sobrepostas enquanto saídas anteriores seguem sem review/merge.

- **Cap global de runs ATIVOS por tenant** (`ROBOTO_WIP_LIMIT`; `0` = sem limite). Atingiu o teto →
  o `claim` de implementação **não pega novo** (fica `QUEUED` até abrir vaga). Determinístico, no
  `store.claim_next_queued(..., wip_limit=N)` (Pg: `COUNT` de ativos; InMemory: idem).
- Aplicado no **dispatch de implementação** (o trabalho delegado que paraleliza); refino/scope/revert
  são leves e não disputam o slot.
- **Visível no cockpit:** a aba **Monitor** mostra **ativos / limite** (trilha M) — o operador vê a
  frota contra o teto.

```mermaid
flowchart LR
  Q[("fila<br/>queued")] --> C{"claim impl"}
  C -->|ativos < WIP| R([vira RUNNING])
  C -->|ativos ≥ WIP| W([espera na fila])
  C -->|issue já ativa| W
```

## 4. Fonte da verdade e follow-ups

A política vive no `claim` (determinística, testada); o teto na config. A verdade do estado segue
na issue + git.

**Follow-ups (backlog):** scheduling **ciente de dependência** (`blocked by` → não executa antes da
bloqueadora mergear); **previsão de sobreposição** por arquivos/área da DoR; **merge queue** +
**test impact analysis** (two-step CI) + **quarentena de flaky** no lado do CI; conflito de merge =
gate humano (trilha H). O custo de LLM do review **não batcheia** → entra no modelo de custo (L).
