# Arquitetura — Vistas C4

> Fase: PESQUISA. Vistas **estruturais no padrão C4** (Context → Container → Component). Os
> diagramas de **processo/estado** (fluxo do SDLC, máquina de estados, escada) vivem em
> [`SYNTHESIS.md`](SYNTHESIS.md) — **complementares**, não C4.
>
> **Rev. 2** — corrigida após a auditoria `audit/architecture-c4` (`research/audits/auditoria-c4.md`,
> PR #19): agentes viraram **componentes dentro do runner** (não contêiner irmão); caminho de **PR
> externo não-confiável** com isolamento forte; feeds/ambiente, Telegram≠observabilidade, estado
> durável do orquestrador, fallback do gateway e rótulos de tecnologia ajustados.

## C4 Nível 1 — Contexto do sistema

```mermaid
C4Context
  title Continuous Development — Nivel 1: Contexto
  Person(dono, "Dono / Revisor", "Aprova gates, prioriza, revisa")
  Person_Ext(contrib, "Contribuidor externo", "Abre PR no repo publico (nao-confiavel)")
  System(cd, "Continuous Development", "Fleet de agentes que cobre o SDLC")
  System_Ext(gh, "GitHub", "Issues, PR, CI/Actions — fonte da verdade")
  System_Ext(orr, "OpenRouter", "Provedor de inferencia / substrato: Claude, chineses, Jev")
  System_Ext(tg, "Telegram", "Notificacao e aprovacao HITL (atalho)")
  System_Ext(feeds, "Feeds de seguranca", "CVE / GHSA / OSV (gatilho ambiente)")
  Rel(dono, gh, "Revisa/aprova (canal canonico)")
  Rel(dono, tg, "Recebe alertas / aprova (revalidado no servidor)")
  Rel(contrib, gh, "Abre PR (nao-confiavel)")
  Rel(cd, gh, "Le/abre issues, abre PR, le CI")
  Rel(cd, orr, "Chama modelos via gateway (right-sizing)")
  Rel(cd, tg, "Notifica / pede aprovacao")
  Rel(feeds, cd, "Alimenta agente de seguranca (ambiente)")
```

> Nota (Trilha I): o externo é **OpenRouter como substrato/provedor** — a palavra "gateway" fica
> reservada ao **contêiner interno** (interface trocável). Jev também tem **API direta** (fallback).

## C4 Nível 2 — Contêineres

```mermaid
C4Container
  title Continuous Development — Nivel 2: Conteineres
  Person(dono, "Dono / Revisor")
  Person_Ext(contrib, "Contribuidor externo")
  System_Ext(gh, "GitHub")
  System_Ext(orr, "OpenRouter (substrato)")
  System_Ext(feeds, "Feeds de seguranca")
  System_Ext(direct, "APIs diretas / LiteLLM / Jev direto", "fallback do gateway")
  System_Ext(tg, "Telegram")
  Container_Boundary(cd, "Continuous Development") {
    Container(orch, "Orquestrador / Dispatcher", "Python + fila/worker", "determinismo: dispatch reativo (evento) e ambiente (feed/schedule); WIP, idempotencia, grafo de dependencias")
    Container(runnerT, "Runner confiavel + agente", "container efemero + git worktree", "codigo NOSSO; 1 por task; hospeda os agentes (Nivel 3)")
    Container(runnerU, "Runner isolado + agente", "microVM gVisor/Firecracker", "PR externo NAO-confiavel; isolamento forte — nao-opcional (K)")
    Container(gw, "Gateway de modelos", "interface/roteador", "escada de validacao; OpenRouter = 1 implementacao + fallback")
    Container(tgbot, "Bot/Notificador Telegram", "Telegram Bot API", "comunicacao + gatilho de conveniencia; autoridade revalidada no servidor")
    Container(obs, "Observabilidade (monitor)", "plataforma decidida na H", "duracao/custo/erros/traces; CONSUMIDA, nao inventada aqui")
    ContainerDb(mem, "Memoria / indice", "markdown+git + FTS5", "fonte da verdade + busca derivada")
    ContainerDb(state, "Estado / run journal", "store externo (durable)", "checkpoint/resume FORA do container efemero (M)")
    ContainerDb(secrets, "Secret store", "Vault / OpenBao", "credenciais curtas, injecao runtime")
  }
  Rel(dono, gh, "Revisa/aprova (canonico)")
  Rel(dono, tgbot, "Alertas / atalho de aprovacao")
  Rel(contrib, gh, "Abre PR")
  Rel(gh, orch, "Webhooks / eventos (reativo)")
  Rel(feeds, orch, "schedule / feed (ambiente)")
  Rel(orch, runnerT, "Dispara job confiavel (JIT)")
  Rel(orch, runnerU, "Dispara PR externo (isolado)")
  Rel(orch, state, "Persiste estado / checkpoint (fora do container)")
  Rel(runnerT, gw, "Pede inferencia")
  Rel(runnerU, gw, "Pede inferencia")
  Rel(gw, orr, "HTTPS")
  Rel(gw, direct, "Fallback")
  Rel(runnerT, mem, "Le/escreve estado")
  Rel(runnerT, gh, "Abre PR / comenta")
  Rel(secrets, runnerT, "Injeta credencial curta")
  Rel(runnerT, obs, "Emite traces / custo")
  Rel(tgbot, dono, "Notifica / coleta aprovacao")
```

## C4 Nível 3 — Componentes (zoom no agente, dentro do runner)

```mermaid
C4Component
  title Agente (dentro do Runner) — Nivel 3: Componentes
  System_Ext(ci, "CI (GitHub Actions)", "tier 1: checks deterministicos — SEM LLM")
  Container(gw, "Gateway de modelos", "tier 2/3: Jev / chineses / Claude")
  ContainerDb(mem, "Memoria / indice")
  Container_Boundary(agent, "Agente (processo no runner)") {
    Component(skill, "Skills", "SKILL.md + scripts", "procedimento por etapa; progressive disclosure")
    Component(tier, "Decisor de tier", "cliente da escada", "decide e DELEGA: tier 1 -> CI; tier 2/3 -> Gateway")
    Component(tools, "Camada de tools", "MCP / CLI", "code-intel (semantico), gh, ripgrep")
    Component(memc, "Cliente de memoria", "", "issue + .md + indice FTS5")
    Component(gwc, "Cliente do gateway", "", "fala com a interface de modelos")
  }
  Rel(skill, tier, "pede decisao de tier")
  Rel(tier, ci, "tier 1: delega check deterministico (lint/test/build)")
  Rel(tier, gwc, "tier 2/3: judge (Jev) / generate")
  Rel(gwc, gw, "chama via interface")
  Rel(skill, tools, "usa (edicao semantica, git, gh)")
  Rel(skill, memc, "le/escreve estado")
  Rel(memc, mem, "le/escreve .md + consulta FTS5")
```

> **Determinismo primeiro**: o **tier 1 é o CI (externo)**, não lógica do agente; o **tier 3 vai pelo
> Gateway (externo)**. O componente interno só **decide o tier e delega** — não "roda os próprios checks".

## Nível 4 (Code) → Esboços ilustrativos das peças

> ⚠️ **Esboços** para comunicar o desenho — **não é código de produção** (fase de pesquisa).

### Peça: Gateway de modelos + escada (a "peça da LLM")
```ts
// A interface do gateway cobre SÓ o que usa modelo. O tier 1 (determinístico) NÃO é do gateway.
interface ModelGateway {
  judge(task): { verdict: "deny"|"ask"|"allow"; confidence: number };   // Jev / jev-guard
  generate(task, model: string): { text: string; confidence?: number };
}

async function routed(task): Result {
  if (task.isDeterministic) return ci.run(task);            // tier 1 — CI EXTERNO, sem LLM (não é do gateway)
  if (task.kind === "decision") return gateway.judge(task); // tier 2 — Jev barato, confiança calibrada
  const cheap = await gateway.generate(task, pickCheapModel(task)); // tier 3a — chinês/aberto
  return cheap.confidence! >= THRESHOLD ? cheap
       : gateway.generate(task, FRONTIER);                  // tier 3b — Claude só se difícil/baixa confiança
}
// OpenRouter é UMA implementação de ModelGateway; fallback: APIs diretas / LiteLLM self-host / Jev direto.
```

### Peça: Gatilho (GitHub Actions → runner JIT) — anti-loop correto (Trilha B)
```yaml
# .github/workflows/agent.yml  (esboço)
on:
  issues: { types: [opened, edited] }
  pull_request: { types: [synchronize] }   # loop DESEJADO fix->review
jobs:
  agent:
    # B: NÃO é filtro-por-actor cego. Ignora eventos do bot EXCETO os que alimentam o loop
    # desejado (bot commita -> CI -> bot corrige); + loop breaker bounded por issue/PR.
    if: ${{ github.actor != 'roboto-bot' || github.event.action == 'synchronize' }}
    runs-on: [self-hosted, roboto-ephemeral]       # runner JIT -> container 1-por-task (K)
    steps:
      - run: assert-loop-budget --key "${{ github.event.issue.number }}" --max 5   # loop breaker (B)
      - uses: ./.github/actions/run-agent
        with: { agent: refinamento, then: validate-readiness }   # gate de prontidão (A)
```

### Peça: Gate de aprovação (Jev + humano; GitHub canônico, Telegram notifica)
```ts
const v = gateway.judge({ action, context });   // deny | ask | allow + confidence
if (v.verdict === "deny") return abort(v);
if (v.verdict === "ask" || v.confidence < HUMAN_THRESHOLD) {
  persistState("PENDING_APPROVAL");              // estado na issue (A) / store durável (M), não no chat
  notifyTelegram(idsResumoSemCodigo);            // dados mínimos (M); canal canônico = GitHub
  await waitApprovalRevalidatedServerSide();     // autoridade verificada no servidor (M/H)
}
```

---
Referências de trilha: estrutura em 0/B/C/I/K; gates/observabilidade em H/M; custo em L; memória em G.
Diagramas de processo/estado: `SYNTHESIS.md`. Auditoria desta vista: `research/audits/auditoria-c4.md` (PR #19).
