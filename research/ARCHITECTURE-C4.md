# Arquitetura — Vistas C4

> Fase: PESQUISA. Este doc traz as **vistas estruturais no padrão C4** (Context → Container →
> Component). Os diagramas de **processo/estado** (fluxo do SDLC, máquina de estados da issue,
> escada de validação) vivem em [`SYNTHESIS.md`](SYNTHESIS.md) — são **complementares**, não C4.
>
> **Nota de padronização (auditoria honesta):** até aqui os diagramas eram `flowchart`/`stateDiagram`
> (processo/estado). C4 descreve **estrutura de software**; por isso ele entra aqui para as vistas
> Contexto/Contêiner/Componente, e os de processo seguem no SYNTHESIS. O nível **Code** do C4 é
> substituído por **esboços ilustrativos** ao final (o que você pediu: exemplo das peças, p.ex. a LLM).

## C4 Nível 1 — Contexto do sistema

```mermaid
C4Context
  title Continuous Development — Nivel 1: Contexto
  Person(dono, "Dono / Revisor", "Aprova gates, prioriza, revisa")
  Person_Ext(contrib, "Contribuidor externo", "Abre PR no repo publico")
  System(cd, "Continuous Development", "Fleet de agentes que cobre o SDLC")
  System_Ext(gh, "GitHub", "Issues, PR, CI/Actions — fonte da verdade")
  System_Ext(orr, "OpenRouter", "Gateway de LLMs: Claude, chineses, Jev")
  System_Ext(tg, "Telegram", "Notificacao e aprovacao HITL")
  System_Ext(feeds, "Feeds de seguranca", "CVE / GHSA / OSV")
  Rel(dono, gh, "Revisa e aprova gates")
  Rel(dono, tg, "Recebe alertas / aprova")
  Rel(contrib, gh, "Abre PR")
  Rel(cd, gh, "Le/abre issues, abre PR, le CI")
  Rel(cd, orr, "Chama modelos (right-sizing)")
  Rel(cd, tg, "Notifica / pede aprovacao")
  Rel(feeds, cd, "Alimenta agente de seguranca (ambiente)")
```

## C4 Nível 2 — Contêineres

```mermaid
C4Container
  title Continuous Development — Nivel 2: Conteineres
  Person(dono, "Dono / Revisor")
  System_Ext(gh, "GitHub")
  System_Ext(orr, "OpenRouter")
  System_Ext(tg, "Telegram")
  Container_Boundary(cd, "Continuous Development") {
    Container(orch, "Orquestrador / Dispatcher", "processo deterministico", "fila, WIP, idempotencia, dispatch por evento, grafo de dependencias")
    Container(runner, "Runner + runtime", "container efemero + git worktree", "1 por task, hospeda os agentes")
    Container(agents, "Fleet de agentes", "skills + subagents", "refinamento, impl, review, seguranca, docs...")
    Container(gw, "Gateway de modelos", "interface", "roteia p/ OpenRouter + fallback (APIs diretas / Jev direto)")
    ContainerDb(mem, "Memoria / indice", "markdown+git + FTS5", "fonte da verdade + busca derivada")
    Container(obs, "Observabilidade + bot Telegram", "monitor", "duracao/custo/erros; notifica/aprova")
    ContainerDb(secrets, "Secret store", "Vault / OpenBao", "credenciais curtas, injecao runtime")
  }
  Rel(dono, gh, "Revisa/aprova (canal canonico)")
  Rel(dono, tg, "Alertas / atalho de aprovacao")
  Rel(gh, orch, "Webhooks / eventos")
  Rel(orch, runner, "Dispara jobs (runner JIT)")
  Rel(runner, agents, "Executa")
  Rel(agents, gw, "Pede inferencia")
  Rel(gw, orr, "HTTPS")
  Rel(agents, mem, "Le/escreve estado")
  Rel(agents, gh, "Abre PR / comenta")
  Rel(runner, secrets, "Injeta credencial curta")
  Rel(obs, tg, "Envia notificacao")
```

## C4 Nível 3 — Componentes (zoom no Agente, ex.: Implementação)

```mermaid
C4Component
  title Agente de Implementacao — Nivel 3: Componentes
  System_Ext(orr, "OpenRouter")
  ContainerDb(mem, "Memoria / indice")
  Container_Boundary(agent, "Agente") {
    Component(skill, "Skills", "SKILL.md + scripts", "procedimento por etapa; progressive disclosure")
    Component(router, "Escada de validacao", "right-sizing", "check deterministico -> Jev -> frontier")
    Component(tools, "Camada de tools", "MCP / CLI", "code-intel (semantico), gh, ripgrep")
    Component(memc, "Cliente de memoria", "", "issue + .md + indice FTS5")
    Component(gwc, "Cliente do gateway", "", "fala com a interface de modelos")
  }
  Rel(skill, router, "decide o tier")
  Rel(router, gwc, "chama o modelo escolhido")
  Rel(gwc, orr, "via gateway")
  Rel(skill, tools, "usa (edicao semantica, git)")
  Rel(skill, memc, "le/escreve estado")
  Rel(memc, mem, "")
```

## Nível 4 (Code) → Esboços ilustrativos das peças

> ⚠️ **Esboços** para comunicar o desenho — **não é código de produção** (fase de pesquisa).

### Peça: Gateway de modelos + escada de roteamento (a "peça da LLM")
```ts
// Interface: a arquitetura fala com ISTO, não com um provedor (desacopla do OpenRouter).
interface ModelGateway {
  deterministic(task): Result;            // (na verdade: nem chama LLM — ver escada)
  judge(task): { verdict: "deny"|"ask"|"allow"; confidence: number };  // Jev / jev-guard
  generate(task, model: string): { text: string; confidence?: number };
}

// Escada de validação / right-sizing (Trilha I)
async function routed(task): Result {
  if (task.isDeterministic) return runCheck(task);          // 1) lint/test/type/build — SEM LLM
  if (task.kind === "decision") return gateway.judge(task); // 2) Jev barato, confiança calibrada
  const cheap = await gateway.generate(task, pickCheapModel(task)); // 3) chinês/aberto
  return cheap.confidence! >= THRESHOLD ? cheap
       : gateway.generate(task, FRONTIER);                  //    escala a Claude só se preciso
}
// OpenRouter é UMA implementação de ModelGateway; fallback: APIs diretas / LiteLLM self-host / Jev direto.
```

### Peça: Gatilho (GitHub Actions → runner JIT no container efêmero)
```yaml
# .github/workflows/refine.yml  (esboço)
on: { issues: { types: [opened, edited] } }
jobs:
  refine:
    if: github.actor != 'roboto-bot'          # anti-loop (Trilha B): ignora o proprio bot
    runs-on: [self-hosted, roboto-ephemeral]  # runner JIT -> container 1-por-task (Trilha K)
    steps:
      - uses: ./.github/actions/run-agent
        with: { agent: refinamento, then: validate-readiness }  # gate de prontidao (Trilha A)
```

### Peça: Gate de aprovação (Jev + humano; GitHub canônico, Telegram notifica)
```ts
const v = gateway.judge({ action, context });   // deny | ask | allow + confidence
if (v.verdict === "deny") return abort(v);
if (v.verdict === "ask" || v.confidence < HUMAN_THRESHOLD) {
  persistState("PENDING_APPROVAL");              // estado na issue (A), nao no chat
  notifyTelegram(idsResumoSemCodigo);            // dados minimos (M); canal canonico = GitHub
  await waitApprovalRevalidatedServerSide();     // autoridade verificada no servidor (M/H)
}
```

---
Referências de trilha: estrutura em 0/B/C/I/K; gates/observabilidade em H/M; custo em L; memória em G.
Diagramas de processo/estado: `SYNTHESIS.md`.
