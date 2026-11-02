# Trilha M — Observabilidade, comunicação e continuidade (como funciona)

> Documento **operacional** (como o sistema funciona hoje). O *porquê* / a investigação fica em
> [`research/M-observabilidade-telegram-checkpoints.md`](https://github.com/CenturyBoys/roboto/blob/main/research/M-observabilidade-telegram-checkpoints.md).
> **Princípio-âncora:** a verdade do estado vive na **issue (A) + git**, não no chat; a autoridade do
> gate é **revalidada no servidor**. **Status:** comunicação + monitor + continuidade no `main`.

## 1. Três capacidades distintas (não confundir)

A pesquisa separa **comunicação**, **observabilidade** e **continuidade** — e dentro de continuidade,
*persistir estado* ≠ *retomar* ≠ *desfazer*.

## 2. Comunicação (Telegram) — já entregue

- **Bot** notifica eventos e coleta aprovação; **conversa** pra refinar demanda (→ materializa em
  issue) e consultar status. **Áudio** (voz → STT → mesmo pipeline).
- **Regras:** allowlist de user ID; o Telegram é **conversa**, a issue é **registro**; toda mutação é
  **proposta revalidada no servidor → GitHub canônico** (D15/D30). Ver [Trilha B](trilha-b-orquestracao.md).

## 3. Monitor da frota (novo)

Observabilidade = a medição das trilhas F/H/L **virada tela**. O cockpit ganhou a aba **Monitor**
(torre de controle), backed por `/overview`:

| Mostra | Fonte |
|---|---|
| runs por **estado** (queued/running/verifying/waiting/done/failed/abandoned) | `store.count_runs_by_state` |
| **ativos** (running+verifying), fila, falhas | idem (zero-fill p/ UI estável) |
| **dead-letters** (itens que falharam após retries) | `store.list_dead_letter` |
| **orçamento do mês** (gasto vs teto, alerta) | trilha L (`spend_since` + `budget.assess`) |

- Auto-refresh (5s) — a frota viva num golpe (`data-testid=fleet-monitor`).
- Determinístico (sem LLM); a verdade segue na issue+git. Custo/comportamento por execução ficam no
  detalhe (trilhas F/L) e na view Custos.
- **Toda ação vira execução visível:** o **Revisar PR** manual, antes síncrono e invisível, agora
  cria um run `review` (feed do veredito + custo medido + PR linkado) — some do "limbo", aparece em
  Execuções/Monitor e **sobrevive a refresh** (o parecer não vivia só no estado do navegador).

## 4. Continuidade — onde o estado vive

- **Persistência leve (default):** estado em **issue + git + run journal** (session_event/feed) —
  resume de alto nível entre etapas. O container é efêmero; o estado durável vive **fora** dele (store).
- **Dead-letter + replay** (trilha B): falha após retries → dead-letter → replay pelo cockpit.
- **Guarda-corpos de intervenção (#157):** enquanto um humano está na **sessão viva**, o sweeper
  **não re-enfileira** o run (`sweep(..., held=hub.live_ids())`) — a intervenção não é interrompida
  nem o estado/lease corrompido.
- **Rollback = `git revert` + reabrir issue** (trilha H) — **resume ≠ rollback**.

## 5. Follow-ups (backlog)

- **Durable execution engine** (Temporal/Restate/LangGraph) só **se** precisar de replay de
  control-flow / wait-states longos em escala (hoje: persistência leve basta).
- **Egress allowlist** explícito do domínio do Telegram + dados mínimos (nunca código/diff/secret).
- **Semântica de timeout** de aprovação (expira → `blocked`/escala) e múltiplos aprovadores (quórum).
