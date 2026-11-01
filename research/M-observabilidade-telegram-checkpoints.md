# Trilha M — Observabilidade operacional, comunicação (Telegram) e checkpoints

> Status: RASCUNHO PARA REVISÃO (criada 2026-10-18 a pedido do dono)

## Pergunta

Como o humano **acompanha e intervém** no fleet em operação: ver jobs/execuções (duração, erros,
logs), ser **notificado e aprovar via Telegram**, e como as execuções **sobrevivem a falha**
(checkpoint/resume)?

## Princípio aplicado

Determinismo primeiro: o **estado da verdade vive na issue (A) + git**, não no chat. "Output do
modelo = proposta; política determinística decide" (H) vale também para aprovações via Telegram.

## 1. Comunicação via Telegram

- **Bot** que (a) **notifica** eventos — job iniciado/concluído/falhou, pedido de aprovação — e
  (b) recebe **aprovações/comandos**.
- **Aprovação HITL**: no checkpoint, o estado é persistido como `PENDING_APPROVAL` (na issue/store,
  **não** no chat); envia mensagem com **task id + resumo da ação + contexto** e **inline keyboard
  Approve/Deny**; resume ao tocar.
- **Segurança**: verificar webhook (secret token do Telegram); **defesa de loopjacking (H)** — a
  mensagem mostra a **ação canônica** e a comparação é exata no momento do uso (o que foi aprovado ==
  o que executa); evitar **double-approval** (idempotência, B); **timeout**; múltiplos aprovadores.
- **Confiabilidade**: poller isolado + **spool durável** de updates de entrada.
- Telegram é **canal**; a verdade do gate vive na issue (A) + política (H). (Dois canais de aprovação
  — Telegram e GitHub — = mais superfície; decidir qual é o canônico.)

## 2. Monitor / dashboard

É a **observabilidade da Trilha H virada tela**: timeline de execução, **duração por job**,
**tokens/custo (L)**, **erros/traces**, mutações de estado.

- Camadas possíveis: (a) o próprio **GitHub** (issues/PRs/Actions) já mostra parte; (b) **plataforma
  de observabilidade** (H) p/ traces de LLM/tool + custo; (c) **dashboard de execução** do runtime
  durável (timeline/event history — ver §3).
- Métricas-chave: duração por job/etapa, custo/token por run (L), taxa de erro, runs em
  andamento/fila (J), **alertas de runaway** (H).

## 3. Checkpoints / durable execution

Sim, é possível — e há padrões estabelecidos. **Durable execution** mantém um run vivo através de
crash/restart: checkpoint de progresso, replay de control flow determinístico, retry de atividades
e **preservação de wait states** (exatamente o que o pause→Telegram→resume precisa).

- **Plataformas**: Temporal, Restate, Inngest, DBOS, Azure Durable Task, Dagster; **LangGraph** tem
  checkpointer (SQLite/Postgres em prod). Padrão 2026: "reasoning graph sobre runtime durável".
- **Nossa escada (determinismo primeiro)**: começar **leve** — checkpoint = **estado na issue (A) +
  run journal + git worktree/branch (K) + memória (G)**; adotar engine durável (Temporal/Restate) só
  se complexidade/escala justificar.
- **Habilita**: resume pós-crash, pausa para aprovação (Telegram), auditoria.
- **Caveat (H)**: resume/rollback tem superfície de ataque (ACRFence; "Safe to Resume?") → **só
  retomar de estado verificado**.

## Amarrações
A (estado na issue) · B (idempotência/orquestração) · G (memória) · H (observabilidade/gates/
loopjacking/rollback) · J (fila/duração) · K (runtime/worktree) · L (custo/latência).

## Perguntas em aberto
- [ ] Checkpoint **leve** (issue + journal + git) basta no MVP, ou adotar **durable execution engine**
      (Temporal/Restate) desde já?
- [ ] **Canal canônico de aprovação**: Telegram, GitHub (review/comment), ou ambos? (dois = mais superfície)
- [ ] O que o **dashboard mostra no MVP** (GitHub + logs) vs. plataforma de observabilidade dedicada?

---

### Fontes
- [Human-in-the-Loop AI Agents with Telegram — dev.to](https://dev.to/jameszh/human-in-the-loop-ai-agents-with-google-adk-and-telegram-5agd)
- [Telegram bot reliability: durable spooling for always-on agents — OpenClaw](https://openclawai.io/blog/openclaw-telegram-bot-reliability-durable-spool)
- [Durable Execution for AI Agents: LangGraph, DBOS, Inngest, Temporal — HackerNoon](https://hackernoon.com/durable-execution-for-ai-agents-langgraph-dbos-inngest-and-temporal-compared)
- [Temporal's LangGraph Plugin — durable execution](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution)
- [AI Agent Workflow Checkpointing and Resumability — zylos.ai](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability/)
