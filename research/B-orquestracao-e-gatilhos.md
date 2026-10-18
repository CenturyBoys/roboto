# Trilha B — Orquestração e gatilhos

> Status: RASCUNHO PARA REVISÃO (executado 2026-10-18)

## Pergunta

Como disparar os agentes do fleet de forma **idempotente, sem loops e barata**, usando eventos do
GitHub como substrato? Onde roda o compute (GitHub Actions vs. webhook server vs. runner na VPS)?

## Taxonomia de gatilho → eventos do GitHub

| Evento GitHub | Tipo | Agente disparado |
|---------------|------|------------------|
| `issues` opened/edited | reativo | **Refinamento** + gate de prontidão (Trilha A) |
| `issues` labeled `status:ready` | reativo | **Planejamento/Arquitetura** |
| `issue_comment` (`@claude` ou aprovação humana) | reativo / sob demanda | **loop de definição** (reprocessa) / responde |
| `pull_request` opened | reativo | **Review** (≠ implementador) |
| `pull_request` synchronize | reativo | **re-Review** (loop fix→review a cada commit) |
| `workflow_run`/`check_suite` failed | reativo | **Implementação** (diagnostica/corrige CI) |
| `pull_request_review` changes_requested | reativo | **Implementação** (endereça o review) |
| `schedule` (cron) + feed externo | **ambiente** | **Segurança** (CVE/GHSA/OSV), drift de docs, deps |
| `workflow_dispatch` | sob demanda | qualquer (humano invoca) |

### Dois modos (padrão do Claude Code GitHub Action)
- **Interativo**: humano menciona `@claude` num comentário → agente responde/age.
- **Automação**: headless em todo evento (PR/push/CI), sem gatilho humano, para gates de qualidade.

## Arquitetura — 3 opções

1. **GitHub Actions + Claude Code (SDK headless)** — zero infra, nativo. `concurrency groups`
   garantem 1 execução por grupo (resto enfileira). Limites: tarefas longas, manejo de secrets,
   e precisa de **machine-user token** para que ações do bot disparem CI downstream.
2. **Webhook server → fila → worker** — FastAPI valida `X-Hub-Signature-256` (HMAC-SHA256),
   **enfileira e responde 200 em <10s** (timeout do GitHub), processamento assíncrono (Celery/Bull).
   Controle total; mais infra.
3. **Self-hosted runner na VPS/container** — o runner puxa jobs pelo 443 (sem porta de entrada
   aberta, pode ficar em rede fechada), escala a zero entre bursts. O LLM roda via API; a VPS só
   hospeda o **harness**.

### Recomendação
Começar com **GitHub Actions disparando um self-hosted runner no nosso container (Trilha K)**:
ganha o wiring de eventos nativo + o runtime controlado que já queremos. Webhook server fica como
evolução se estourarmos os limites do Actions (tarefas muito longas / orquestração complexa).

> **Modelo de runner**: usar **ephemeral/JIT runners** (registram just-in-time por job e se
> desregistram) — é o que casa o Actions com o container 1-por-task da Trilha K. Alternativa: runner
> persistente que **spawna** containers efêmeros (dois níveis). O "efêmero por task" exige um desses
> desenhos explícitos, não o runner persistente padrão.

## Regras de confiabilidade (determinismo primeiro — quase tudo sem LLM)

Entrega é **at-least-once** (webhook/queue reentregam) → efeitos precisam ser **idempotentes**:
- [ ] **Idempotency key por arquitetura**: no **webhook server**, `X-GitHub-Delivery`; no **GitHub
      Actions** (a recomendação) não há esse header → usar `head_sha` + tipo de evento + nº da issue/PR.
      Grava antes de processar; se já visto, descarta.
- [ ] **Enfileirar** tarefas longas (não processar inline no handler de 10s).
- [ ] **Retry com backoff exponencial** + **dead-letter** com contexto + **replay** após fix.
- [ ] **Concurrency group** por issue/PR para serializar.

## Prevenção de loop infinito (ponto levantado pelo dono)

Ação do bot **não pode** re-disparar o bot:
- [ ] **Filtrar por actor com exceções**: ignorar eventos do bot **exceto** os que alimentam o loop
      desejado (bot commita → CI → bot corrige). Distinguir "loop desejado (bounded pelo contador)" de
      "loop infinito" por tipo de evento — não um filtro-por-actor cego (que mataria o loop fix→review).
- [ ] **Gate de confiança**: automação só para autores/labels confiáveis (crítico em repo público —
      conteúdo de PR não confiável pode tentar **prompt injection**; ver Trilha H e o case da Microsoft).
- [ ] **Loop breaker**: contador máximo de iterações por issue/PR (o loop de definição e o
      fix→review precisam ser **bounded**).

## Amarrações com outras trilhas
- **Scheduling ciente de dependência** (Trilha J): o orquestrador checa `blocked by` antes de despachar.
- **Agentes ambiente** (Trilha 0): `schedule` + feed; ou daemon longo na VPS.
- **Gate de prontidão / loop de comentário** (Trilha A): `issue_comment` reprocessa.
- **Runtime** (Trilha K): onde o runner/daemon vive.

## Perguntas em aberto
- [ ] Machine-user dedicado (identidade do bot) — qual, com que escopo mínimo?
- [ ] Actions-only no MVP, ou já subir o runner no container desde o início?
- [ ] Feeds do agente ambiente: cron no Actions vs. daemon na VPS?

---

### Fontes
- [Claude Code as a GitHub-Native Agent: Issue-to-Merge Loop — saulius.io](https://saulius.io/blog/claude-code-github-native-agent-issue-to-merge-loop)
- [Running Claude Code in CI: Headless Mode & GitHub Actions — AgentsCamp](https://agentscamp.com/guides/advanced/claude-code-ci-github-actions)
- [Securing CI/CD in an agentic world: Claude Code GitHub Action case — Microsoft](https://www.microsoft.com/en-us/security/blog/2026/06/05/securing-ci-cd-in-agentic-world-claude-code-github-action-case/)
- [Webhook-Driven Agent Architecture (idempotency, retries, DLQ) — buildmvpfast](https://www.buildmvpfast.com/blog/webhook-driven-agent-architecture-event-based-triggers-autonomous-ai-workflows-2026)
- [p08-event-automation: idempotent execution, retry/backoff, dead-letter, replay — GitHub](https://github.com/Murasimu/p08-event-automation)
- [Self-Hosted GitHub Runners on AWS Spot for AI Dev Teams — kane.mx](https://kane.mx/posts/2026/self-hosted-github-runners-aws-spot/)
- [Put an AI Agent Behind a Webhook: GitHub Issues → PRs — Developers Digest](https://www.developersdigest.tech/blog/deploy-agent-webhook-railway)
