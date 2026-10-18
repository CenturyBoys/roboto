# Trilha M — Observabilidade operacional, comunicação (Telegram) e continuidade

> Status: RASCUNHO PARA REVISÃO (criada 2026-10-18; reescrita após auditoria `audit/trilha-m` / PR #18)
>
> ✅ **Decidido** (ver `DECISOES-A-FECHAR.md`): **Telegram no MVP** (refinamento conversacional →
> materializa issue) (D2); **GitHub = canal canônico de gate**, Telegram = atalho revalidado (D15);
> **checkpoint leve** issue+git+journal (D5).

> 🧩 Checkpoint/resume (estado no banco) e efeitos via outbox: ver [`DESIGN-nucleo.md`](DESIGN-nucleo.md).

## Pergunta

Como o humano **acompanha, conversa e intervém** no fleet em operação: ver jobs/execuções (duração,
erros, logs), **conversar via Telegram** (notificar/aprovar e **refinar demandas / consultar o
backlog** — além de issues e eventos), e como uma execução **sobrevive a falha** sem confundir
*persistir estado*, *retomar* e *desfazer*?

## Princípio aplicado

Determinismo primeiro: a **verdade do estado vive na issue (A) + git**, não no chat. "Output do
modelo = proposta; política determinística decide" (H) — e **a autoridade do gate é verificada no
servidor**, nunca delegada a um toque de botão em app de terceiro.

## Três capacidades distintas (não confundir)

A auditoria pegou a confusão original. São **três coisas separadas**:

1. **Comunicação (porta bidirecional via Telegram)** — notificar, coletar aprovação **e conversar**
   (refinar demandas, consultar backlog) — além de issues/eventos.
2. **Observabilidade** (monitor) — ver o que aconteceu/está acontecendo.
3. **Continuidade de execução** — e aqui há **três mecanismos diferentes**:
   - **Persistência de estado**: issue + git + run journal guardam *onde parou* (resume de alto
     nível, entre etapas). **NÃO é** durable execution.
   - **Durable execution (engine)**: Temporal/Restate/LangGraph fazem **replay de control-flow e
     preservam wait-states** *dentro* de um run longo. Mecanismo distinto, não "um tamanho maior" do anterior.
   - **Rollback**: desfazer efeitos — **default já decidido na H: `git revert` + reabrir issue**;
     checkpoint sofisticado só como exceção. **Resume (retomar) ≠ rollback (desfazer).**

## 1. Comunicação via Telegram

- **Bot** notifica eventos (job iniciado/concluído/falhou, pedido de aprovação) e coleta aprovação
  (inline keyboard Approve/Deny).
- **Porta de comunicação bidirecional (ideia do dono — além de issues/eventos)**: o Telegram também
  é um canal de **conversa** com o fleet, para dar agilidade sem abrir o GitHub:
  - **Refinamento conversacional**: o dono descreve/discute uma demanda no chat; o agente de
    Refinamento ajuda a moldar → o resultado **materializa numa issue do GitHub** (fonte da verdade).
    O chat é **entrada**, não o registro.
  - **Consulta / Q&A**: perguntar status, o que falta, **demandas ainda não feitas** (leitura sobre
    issues/Projects) direto do Telegram.
  - Mesmas regras: **user ID na allowlist**, **dados mínimos**, e qualquer **mutação de estado**
    (criar issue, iniciar trabalho, aprovar) é **proposta revalidada no servidor → GitHub canônico**.
- **Autenticação do aprovador (finding alto)**: o secret do webhook autentica o **canal**, não
  **quem clica**. Exigir: **allowlist de Telegram user IDs** autorizados; política de **conta
  comprometida** (revogação); e — crítico — a aprovação do Telegram é só um **gatilho de
  conveniência**: a **autoridade canônica é revalidada no servidor** contra o estado da issue e a
  política (H). Um toque no chat **não** pode, sozinho, aprovar merge/deploy.
- **Minimização de dados (finding alto)**: notificação carrega **só IDs + resumo curto**, **nunca
  código, diff ou secret**; o domínio do Telegram precisa estar **explicitamente no allowlist de
  egress** (senão colide com o deny-all da K); dados sensíveis **não vão ao Telegram** (bots não são E2E).
- **Defesa de loopjacking (herdada de H)**: a mensagem mostra a **ação canônica** e a comparação é
  **exata no momento do uso** (o aprovado == o executado); anti-double-approval via idempotência (B); timeout.
- Confiabilidade: poller isolado + spool durável de updates.

## 2. Monitor / observabilidade

**Não é uma plataforma nova** — é a **observabilidade da Trilha H virada tela**. Dono da decisão de
plataforma = **H** (uma escolha única que M e L consomem).

- Mostra: timeline de execução, **duração por job/etapa**, **tokens/custo (L)**, erros/traces,
  runs em andamento/fila (J), alertas de **runaway** (H).
- Camadas: GitHub (issues/PRs/Actions) já cobre parte → plataforma de observabilidade (H) para
  traces de LLM/tool + custo.
- **A própria observabilidade tem custo** (ingestão/retenção) → entra no orçamento (L).

## 3. Continuidade — onde o estado vive

- **Persistência leve (default MVP)**: estado em **issue (A) + git worktree/branch (K)** + **run
  journal = comentários estruturados na issue / traces na plataforma de observabilidade (H)** — não
  é artefato órfão novo. Permite **resume de alto nível** entre etapas.
- **Durable execution engine** (Temporal/Restate/LangGraph): adotar **só se** precisarmos de replay
  de control-flow / wait-states longos / pause→aprovação→resume robusto em escala.
- **Reconciliação com o runtime efêmero (K)**: o container é **1-por-task e efêmero**; portanto o
  **estado durável vive FORA do container** (store externo / camada do orquestrador) — um container
  novo **retoma do checkpoint externo**. Engine durável ≠ container de vida longa.
- **Caveat (H)**: resume/rollback tem superfície de ataque (ACRFence; "Safe to Resume?") → **só
  retomar de estado verificado**.

## Opções e trade-offs

| Decisão | Opção A | Opção B | Recomendação |
|---------|---------|---------|--------------|
| Canal canônico de aprovação | **GitHub** (review/comment/estado da issue) | Telegram | **GitHub é canônico**; Telegram = notifica + atalho que **revalida no servidor** |
| Continuidade | Persistência leve (issue+git+journal) | Durable execution engine | **Leve no MVP**; engine só quando escala/replay exigir |

## Recomendação

Telegram como **notificador + gatilho de conveniência** (allowlist de user ID, dados mínimos, egress
explícito, revalidação server-side); **GitHub como canal canônico de gate**. Monitor = a plataforma
de observabilidade **decidida na H**, exibindo duração/custo/erros. Continuidade = **persistência
leve (issue+git+journal) no MVP**, com estado durável **fora** do container efêmero; engine durável
só se justificar. **Resume ≠ rollback**; rollback segue o default da H (`git revert` + reabrir issue).

## Impacto em token
- Notificação/aprovação e monitor são **determinísticos** (sem LLM) → custo de token ~zero.
- Persistência/checkpoint é estado, não geração → não gasta token; evita **re-trabalho** (re-executar
  do zero após falha), o que **economiza** token. A observabilidade de custo (L) é o que torna isso mensurável.

## Perguntas em aberto
- [ ] Persistência leve basta no MVP, ou já adotar durable execution engine? (recomendação: leve)
- [ ] Qual plataforma de observabilidade (decisão **da H**, consumida aqui).
- [ ] Semântica de **timeout** (expira → volta a `blocked`/escala?) e **múltiplos aprovadores**
      (quórum vs. primeiro-a-responder).

---

### Fontes
> Disciplina de fontes: as abaixo são **secundárias/indicativas** (blog/vendor). As primárias que
> sustentam a parte de segurança são **herdadas da Trilha H** e verificadas lá:
> loopjacking (arXiv 2609.21081) e ACRFence (arXiv 2603.20625).

- [Human-in-the-Loop AI Agents with Telegram — dev.to](https://dev.to/jameszh/human-in-the-loop-ai-agents-with-google-adk-and-telegram-5agd) *(indicativo)*
- [Telegram bot reliability: durable spooling — OpenClaw](https://openclawai.io/blog/openclaw-telegram-bot-reliability-durable-spool) *(indicativo)*
- [Durable Execution for AI Agents: LangGraph/DBOS/Inngest/Temporal — HackerNoon](https://hackernoon.com/durable-execution-for-ai-agents-langgraph-dbos-inngest-and-temporal-compared) *(indicativo)*
- [Temporal's LangGraph Plugin — durable execution](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) *(vendor, indicativo)*
- [Loopjacking (arXiv 2609.21081)](https://arxiv.org/abs/2609.21081) · [ACRFence (arXiv 2603.20625)](https://arxiv.org/abs/2603.20625) — primárias, via Trilha H
