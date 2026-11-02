# Trilha G — Memória e second brain (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/G-memoria-e-second-brain.md`](https://github.com/CenturyBoys/roboto/blob/main/research/G-memoria-e-second-brain.md).
> **Princípio-âncora:** memória **determinística e auditável** — separar **storage** (fonte da
> verdade) de **search** (índice derivado, rebuildável). Recall **sem LLM**.
> **Status:** remember/recall com FTS + **injeção de memória no implement** (continuidade) no `main`.

## 1. O que a trilha entrega

Continuidade entre runs/agentes **sem sessão gigante**: o fleet lembra decisões/fatos e os traz de
volta quando são relevantes — em vez de carregar histórico inteiro no contexto (contra a trilha F).

## 2. Storage × search (separados)

| Camada | O que é | Onde |
|---|---|---|
| **storage** (verdade) | fatos/decisões — issue + repo + registros | `store.remember` (kind: fato/decisão/handoff) |
| **search** (derivado) | recall **determinístico, sem LLM** | PgStore: FTS `ts_rank` · InMemory: overlap de termos |

O search é **cache**: se o índice some, rebuilda a partir dos registros. Recuperação barata (trilha F)
e auditável (trilha H).

## 3. Como a memória entra no trabalho (harness-driven)

Mesma régua de E/F: o **harness recalla e injeta** — não depende do modelo lembrar.

```mermaid
flowchart LR
  F[("fatos/decisões<br/>store.remember")] -->|recall(query)| R["recall_block<br/>(capado por token)"]
  R --> SC["prompt de scope<br/>(montar issue)"]
  R --> IM["prompt de implement<br/>(codar)"]
```

- **`app/memory.recall_block`**: recalla os fatos relevantes pra uma query e formata um bloco
  **capado** por orçamento de token. Vazio quando não há nada (não polui o prompt).
- **Scope** (montar issue) e **implement** (codar) injetam o bloco — o implement usa o título + corpo
  da issue como query. Isolado por tenant (D17).
- Fontes de fato hoje: **perfil do repo** no boot, **`@potter lembra <texto>`** (manual). O conjunto
  cresce com o uso.

## 4. Formato e fonte da verdade

Fato curto e bounded, com `kind` (fato / decisão / handoff) e `ref` (issue/PR). O recall é um índice
derivado — a fonte da verdade são os registros + o repo + as issues (git-first, com rollback nativo).

## 5. Follow-ups (backlog)

- **Markdown-first**: fatos como `.md` versionados no `roboto` (`memory/`) + FTS5 derivado — hoje o
  storage é o banco; migrar pra arquivos dá git/rollback/greppável.
- **Auto-remember** de decisões/fixes ao fim de um ciclo (hoje o fato é manual via `@potter lembra`).
- **Framework externo** (Zep/Mem0) só como **exceção** medida contra o default (raciocínio temporal
  ou escala cross-session que arquivos+índice não deem conta) — avaliar via golden set (trilha H).
