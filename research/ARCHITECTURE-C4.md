# Arquitetura — Vistas C4 + Sequências

> Fase: PESQUISA. **Rev. 4** — estilo (cores por tipo + layout) e **profundidade** (componentes do
> Orquestrador + vista de Deployment). Diagramas pequenos e focados. Correções da auditoria (PR #19) mantidas.
>
> Paleta: **azul** = nosso sistema/contêiner · **verde-água** = armazenamento · **cinza** = externo ·
> **vermelho** = fronteira não-confiável (isolamento forte). Render do mermaid varia por viewer.

---

## C4 Nível 1 — Contexto

```mermaid
C4Context
  title Nivel 1 — Contexto
  Person(dono, "Dono / Revisor")
  Person_Ext(contrib, "Contribuidor externo", "PR nao-confiavel")
  System(cd, "Continuous Development", "Fleet de agentes do SDLC")
  System_Ext(gh, "GitHub")
  System_Ext(orr, "OpenRouter", "substrato de modelos")
  System_Ext(tg, "Telegram")
  System_Ext(feeds, "Feeds de seguranca")
  Rel(dono, gh, "aprova (canonico)")
  Rel(dono, tg, "alertas / aprova")
  Rel(contrib, gh, "abre PR")
  Rel(cd, gh, "issues / PR / CI")
  Rel(cd, orr, "inferencia")
  Rel(cd, tg, "notifica")
  Rel(feeds, cd, "ambiente")
  UpdateElementStyle(cd, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateElementStyle(contrib, $bgColor="#B5433A", $fontColor="#ffffff", $borderColor="#7D2B25")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## C4 Nível 2 — Contêineres (3 fatias)

### 2a · Entrada e orquestração
```mermaid
C4Container
  title Nivel 2a — Entrada e orquestracao
  System_Ext(gh, "GitHub")
  System_Ext(feeds, "Feeds")
  Container_Boundary(cd, "Continuous Development") {
    Container(orch, "Orquestrador", "fila / worker", "dispatch, WIP, idempotencia, dependencias")
    Container(runnerT, "Runner confiavel", "container efemero", "codigo nosso")
    Container(runnerU, "Runner isolado", "microVM gVisor", "PR externo")
    ContainerDb(state, "Estado / journal", "store durable", "checkpoint fora do container")
  }
  Rel(gh, orch, "webhook (reativo)")
  Rel(feeds, orch, "schedule (ambiente)")
  Rel(orch, runnerT, "job confiavel")
  Rel(orch, runnerU, "PR externo")
  Rel(orch, state, "checkpoint / resume")
  UpdateElementStyle(orch, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateElementStyle(runnerU, $bgColor="#B5433A", $fontColor="#ffffff", $borderColor="#7D2B25")
  UpdateElementStyle(state, $bgColor="#2E7D6F", $fontColor="#ffffff", $borderColor="#1C5349")
  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

### 2b · Execução e modelos
```mermaid
C4Container
  title Nivel 2b — Execucao e modelos
  System_Ext(gh, "GitHub")
  System_Ext(orr, "OpenRouter")
  System_Ext(direct, "APIs diretas / Jev direto", "fallback")
  Container_Boundary(cd, "Continuous Development") {
    Container(runner, "Runner + agente", "container efemero", "hospeda agentes (N3)")
    Container(gw, "Gateway de modelos", "interface / roteador", "escada de validacao")
    ContainerDb(mem, "Memoria / indice", "md+git + FTS5")
    ContainerDb(secrets, "Secrets", "Vault / OpenBao")
  }
  Rel(runner, gw, "inferencia")
  Rel(gw, orr, "HTTPS")
  Rel(gw, direct, "fallback")
  Rel(runner, mem, "le / escreve")
  Rel(runner, gh, "abre PR")
  Rel(secrets, runner, "credencial curta")
  UpdateElementStyle(gw, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateElementStyle(mem, $bgColor="#2E7D6F", $fontColor="#ffffff", $borderColor="#1C5349")
  UpdateElementStyle(secrets, $bgColor="#2E7D6F", $fontColor="#ffffff", $borderColor="#1C5349")
  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

### 2c · Humano e observabilidade
```mermaid
C4Container
  title Nivel 2c — Humano e observabilidade
  Person(dono, "Dono / Revisor")
  System_Ext(tg, "Telegram")
  Container_Boundary(cd, "Continuous Development") {
    Container(runner, "Runner + agente", "", "emite sinais")
    Container(obs, "Observabilidade", "plataforma da Trilha H", "duracao / custo / erros")
    Container(tgbot, "Bot Telegram", "Bot API", "notifica + atalho de aprovacao")
  }
  Rel(runner, obs, "traces / custo")
  Rel(runner, tgbot, "pede aprovacao / avisa")
  Rel(tgbot, tg, "via Bot API")
  Rel(tg, dono, "Approve / Deny")
  Rel(obs, dono, "dashboard")
  UpdateElementStyle(obs, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateElementStyle(tgbot, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## C4 Nível 3 — Componentes

### 3a · Agente (dentro do runner)
```mermaid
C4Component
  title Nivel 3a — Agente
  System_Ext(ci, "CI", "tier 1: sem LLM")
  Container(gw, "Gateway", "tier 2/3")
  ContainerDb(mem, "Memoria")
  Container_Boundary(agent, "Agente") {
    Component(skill, "Skills", "SKILL.md")
    Component(tier, "Decisor de tier", "delega, nao executa")
    Component(tools, "Tools", "code-intel / gh")
    Component(memc, "Cli. memoria", "")
    Component(gwc, "Cli. gateway", "")
  }
  Rel(skill, tier, "decide tier")
  Rel(tier, ci, "tier 1 -> CI")
  Rel(tier, gwc, "tier 2/3")
  Rel(gwc, gw, "chama")
  Rel(skill, tools, "usa")
  Rel(skill, memc, "estado")
  Rel(memc, mem, "le/escreve")
  UpdateElementStyle(tier, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

### 3b · Orquestrador (interno) — profundidade
```mermaid
C4Component
  title Nivel 3b — Orquestrador
  System_Ext(gh, "GitHub")
  Container(runner, "Runner")
  ContainerDb(state, "Estado/journal")
  Container_Boundary(o, "Orquestrador") {
    Component(ev, "Event handler", "valida webhook")
    Component(idem, "Idempotencia", "head_sha + evento")
    Component(dep, "Scheduler dependencia", "blocked-by / colisao")
    Component(wip, "WIP / backpressure", "limite concorrencia")
    Component(disp, "Dispatcher", "escolhe runner T / U")
  }
  Rel(gh, ev, "evento")
  Rel(ev, idem, "chave")
  Rel(idem, dep, "nao-visto")
  Rel(dep, wip, "desbloqueado")
  Rel(wip, disp, "slot livre")
  Rel(disp, runner, "dispara (T ou U)")
  Rel(disp, state, "checkpoint")
  UpdateElementStyle(disp, $bgColor="#1168BD", $fontColor="#ffffff", $borderColor="#0B4884")
  UpdateElementStyle(state, $bgColor="#2E7D6F", $fontColor="#ffffff", $borderColor="#1C5349")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## C4 Deployment — runtime / infra (profundidade)

```mermaid
C4Deployment
  title Deployment — onde cada coisa roda
  Deployment_Node(vps, "VPS / host", "Linux + Docker") {
    Deployment_Node(svc, "Servico sempre-ligado", "") {
      Container(orch, "Orquestrador", "fila/worker")
    }
    Deployment_Node(jit, "Runner JIT (por task)", "") {
      Deployment_Node(ctr, "Container efemero", "nao-root, read-only, egress allowlist") {
        Container(agentT, "Agente (confiavel)", "")
      }
      Deployment_Node(uvm, "microVM gVisor/Firecracker", "PR externo nao-confiavel") {
        Container(agentU, "Agente (isolado)", "")
      }
    }
  }
  Deployment_Node(cloud, "Externo (SaaS)", "") {
    System_Ext(orr, "OpenRouter")
    ContainerDb(state, "Estado / journal", "store durable")
  }
  Rel(orch, agentT, "dispara")
  Rel(orch, agentU, "dispara (isolado)")
  Rel(agentT, orr, "inferencia (via gateway)")
  Rel(orch, state, "checkpoint")
  UpdateElementStyle(agentU, $bgColor="#B5433A", $fontColor="#ffffff", $borderColor="#7D2B25")
  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```

---

## Sequências (comportamento + decisões)

### S1 · Issue → PR → merge
```mermaid
sequenceDiagram
  autonumber
  actor Dono
  participant GH as GitHub
  participant Orq as Orquestrador
  participant Ag as Agente
  participant CI
  Dono->>GH: abre issue
  GH->>Orq: evento
  Orq->>Ag: Refinamento (DoR)
  alt falta definicao
    Ag-->>GH: pede clarificacao (loop)
  else pronta
    Orq->>Ag: Planejamento + Implementacao
    Ag->>GH: abre PR
    GH->>CI: checks tier 1 (sem LLM)
    Orq->>Ag: Review (agente != autor)
    alt DoD ok + gate humano
      Dono->>GH: aprova merge
    else falha de gate
      Orq->>Ag: volta a Implementacao
    end
  end
```

### S2 · Gate de aprovação (Jev + Telegram, revalidado no servidor)
```mermaid
sequenceDiagram
  autonumber
  participant Ag as Agente
  participant Pol as Politica (Jev)
  participant St as Estado (issue)
  participant TG as Bot Telegram
  actor Dono
  Ag->>Pol: acao proposta
  Pol-->>Ag: deny | ask | allow (+confianca)
  alt allow e confianca alta
    Ag->>Ag: executa
  else ask ou confianca baixa
    Ag->>St: PENDING_APPROVAL
    Ag->>TG: notifica (IDs+resumo, sem codigo)
    TG->>Dono: Approve/Deny
    Dono->>TG: toque
    TG->>St: registra decisao
    St->>Ag: revalida no servidor (acao == aprovado)
  end
```

### S3 · Checkpoint / resume pós-falha
```mermaid
sequenceDiagram
  autonumber
  participant Orq as Orquestrador
  participant R as Runner efemero
  participant St as Estado/journal
  Orq->>R: dispara task
  R->>St: checkpoint (progresso)
  R--xOrq: crash
  Orq->>St: le ultimo checkpoint verificado
  Orq->>R: novo container retoma (resume)
  note over Orq,St: desfazer efeitos = rollback (git revert + reabrir issue, Trilha H)
```

---

## Esboços de implementação (ilustrativos, não-produção)

<details><summary>Gateway + escada · gatilho anti-loop · gate de aprovação</summary>

```ts
interface ModelGateway {               // SÓ o que usa modelo; tier 1 NÃO é do gateway
  judge(task): { verdict: "deny"|"ask"|"allow"; confidence: number };   // Jev
  generate(task, model: string): { text: string; confidence?: number };
}
async function routed(task) {
  if (task.isDeterministic) return ci.run(task);                   // tier 1 — CI externo, sem LLM
  if (task.kind === "decision") return gateway.judge(task);        // tier 2 — Jev
  const cheap = await gateway.generate(task, pickCheapModel(task)); // tier 3a — chinês/aberto
  return cheap.confidence! >= T ? cheap : gateway.generate(task, FRONTIER); // tier 3b — Claude
}
```
```yaml
# anti-loop CORRETO (B): filtro por actor COM exceções + loop breaker — não filtro cego
on: { issues: { types: [opened, edited] }, pull_request: { types: [synchronize] } }
jobs:
  agent:
    if: ${{ github.actor != 'roboto-bot' || github.event.action == 'synchronize' }}
    runs-on: [self-hosted, roboto-ephemeral]
    steps:
      - run: assert-loop-budget --key "${{ github.event.issue.number }}" --max 5
      - uses: ./.github/actions/run-agent
```
```ts
const v = gateway.judge({ action, context });
if (v.verdict === "deny") return abort(v);
if (v.verdict === "ask" || v.confidence < HUMAN_THRESHOLD) {
  persistState("PENDING_APPROVAL");            // na issue (A), não no chat
  notifyTelegram(idsResumoSemCodigo);          // dados mínimos (M); gate canônico = GitHub
  await waitApprovalRevalidatedServerSide();   // autoridade no servidor (M/H)
}
```
</details>

---
Estrutura: 0/B/C/I/K · gates/observabilidade: H/M · custo: L · memória: G. Auditoria: `research/audits/auditoria-c4.md` (PR #19).
