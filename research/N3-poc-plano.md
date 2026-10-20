# Trilha N3 · Plano de PoC — motor vivo contra repo real (jo-ken-po)

> Valida o contrato `CodingEngine` (D22) e o loop interativo **contra um repositório real**, com o
> motor **Claude Code** backeado por **OpenRouter/Qwen** via **claude-code-router**, tudo isolado
> num **Docker**. Decisões do dono: Qwen3-coder (big) / Qwen2.5 (small); Docker com Playwright;
> usar recursos da máquina.

## 1. Cenário (alvo)
- **Repo:** `jo-ken-po` → remote **`github.com/arenavalendo/main`**. É um **scaffold reutilizável**
  (não app de domínio): monorepo pnpm+Turborepo, Next.js App Router + TS strict, Prisma/Postgres,
  Redis/BullMQ, PWA, i18n, RBAC; GitFlow + TDD + Conventional Commits; CI rica (`ci/e2e/security`).
- **Agent-ready:** já tem `AGENTS.md` (convenções canônicas), `CLAUDE.md`, `.claude/`, ADRs. O
  entendimento do repo é **por-run do agente** (lê o `AGENTS.md` no checkout), não da config.

## 2. Roteamento de modelo (Qwen via OpenRouter)
- **Motor (Claude Code):** fala API Anthropic → apontar `ANTHROPIC_BASE_URL` para o
  **claude-code-router (ccr)** → ccr traduz p/ **OpenRouter**. Mapa: *default/main* →
  `qwen/qwen3-coder`; *background/small* → `qwen/qwen-2.5-72b-instruct` (`poc/ccr.config.json`).
- **Gateway nativo do roboto (refino/judge):** `OpenRouterGateway` já aponta p/ Qwen (mesmos ids).
- A chave real é a `OPENROUTER_API_KEY` (na config do ccr); o `ANTHROPIC_API_KEY` que o Claude Code
  usa é fake (o ccr ignora).

## 3. Ambiente — Docker único isolado (`poc/`)
Imagem base **Playwright** (Node + browsers + libs de e2e) + pnpm + Python/`roboto` + Claude Code CLI
+ ccr. `compose.poc.yml` sobe **Postgres** + o container do PoC. O container: (1) sobe o ccr, (2)
clona o repo-alvo em `/work/target`, (3) roda o `roboto` daemon. Isolado; usa recursos da máquina.
Arquivos: `poc/Dockerfile`, `poc/compose.poc.yml`, `poc/ccr.config.json`, `poc/.env.poc.example`,
`poc/entrypoint.sh`. ⚠️ versões (tag Playwright, pacote/porta do ccr, flag `--break-system-packages`)
são **a validar no primeiro build** — não deu pra exercitar sem rede/segredos.

## 4. Peças ainda a construir (gaps que o PoC expôs)
1. ✅ **`process_run_tick`** (claim da fila → `drive_turn` do motor) — feito e testado com `StubEngine`.
2. ⏳ **`ClaudeCodeEngine`** real (adapter do contrato via Agent SDK/CLI, stream→`EngineEvent`,
   aprovação via `can_use_tool`, resume por `session_id`) — **próximo PR**. Precisa do SDK instalado.
3. ⏳ **Wiring no `runtime`**: selecionar motor por `ROBOTO_ENGINE` (`stub`|`claude_code`) e adicionar
   o laço `process_run_tick`. Hoje o daemon roda poll/outbox/sweeper; falta plugar o laço de runs.
4. ⏳ **git worktree por run** (checkout isolado, branch por issue) no runner — K.

## 4.1 Fase 0 ✅ (2026-10-20) + achados validados
Fase 0 passou no container: build (base **noble**/Python 3.12 + venv), Postgres, smoke claim→motor
(StubEngine → VERIFYING), ferramentas: node 20.18, pnpm 9.12, Python 3.12.3, **Claude Code 2.1.197**,
**claude-code-router 2.0.0**, Playwright 1.64.1. Validações que destravam a Fase 1:
- **SDK:** `claude-agent-sdk==0.2.168` (bundla o CLI); `query()`/`ClaudeAgentOptions(cwd/permission_mode/
  resume/model)` e blocks `TextBlock.text`/`ToolUseBlock.name`/`ResultMessage.session_id/usage`
  confirmados. **`ResultMessage` usa `subtype` (não `is_error`)** — adapter corrigido.
- **ccr v2.0.0:** provider OpenRouter exige `transformer:{use:["openrouter"]}`; `NON_INTERACTIVE_MODE:true`
  p/ headless; `api_base_url` termina em `/chat/completions`; porta **3456**; `ANTHROPIC_BASE_URL=
  http://127.0.0.1:3456` + setar `ANTHROPIC_API_KEY` **e** `ANTHROPIC_AUTH_TOKEN`. ccr.config.json corrigido.

## 5. Fases
- **Fase 0 — encanamento (sem LLM):** Docker builda; Postgres sobe; daemon sobe; clona jo-ken-po;
  `StubEngine` percorre claim→drive→(WAITING/VERIFYING); `pnpm install && pnpm test`/Playwright
  rodam no container. **Prova a infra** sem gastar token nem tocar o GitHub.
- **Fase 1 — motor vivo:** `ClaudeCodeEngine` via ccr→Qwen. Uma **issue pequena** no jo-ken-po →
  branch → implementação → PR → **CI do jo-ken-po** (o juiz real) → review. Gate humano no merge.

## 6. Feature de teste (apurado) — escolher pequeno, subir o risco aos poucos
Candidatas (ordem de risco crescente; começar pela 1):
1. **Pure function em `packages/core` + teste (TDD).** Ex.: um helper determinístico com casos de
   borda. Toca 1 pacote, sem UI/DB/infra. **Ideal como primeira.**
2. **Route handler / Server Action pequena** validada com Zod (borda) + teste.
3. **Mudança de UI** (shadcn) tocando `apps/web` + e2e Playwright.

**DoR (pronto p/ começar):** issue com **critério de aceite** claro e verificável; escopo em 1 pacote;
sem decisão arquitetural nova (senão exige ADR). **DoD (pronto):** `pnpm lint`+`typecheck`+testes
**verdes no CI do jo-ken-po**; PR aberto seguindo **Conventional Commits** e GitFlow; convenções do
`AGENTS.md` respeitadas; nada commitado direto em `main`/`develop` (sempre branch+PR); gate humano no merge.

## 7. Critérios de sucesso (validam a matriz do D22, N2)
| Capacidade | Como verifico no PoC |
|---|---|
| Start headless | motor inicia com cwd=checkout, sem login interativo |
| Stream de eventos | eventos chegam como `EngineEvent` (mensagem/tool/finished) |
| **Aprovação por ação** | uma ação sensível (ex.: comando) vira `NEEDS_APPROVAL` → pergunta no Telegram |
| **Pausa/retomada** | responder a interação → `resume` da sessão continua o trabalho |
| Resume sobrevive a restart | matar o container no meio e retomar pelo `native_session_id` |
| Resultado + custo | `ResultMessage`/usage mapeado p/ `llm_call` (D10) |
| Cancelar | `interrupt()` para a execução |

## 8. Riscos (de N2) a observar no PoC
- **Aprovação fina**: `can_use_tool` do Claude Code não dispara p/ tools pré-aprovadas → configurar
  `permission_mode=default` + allowlist mínima; medir se o gate humano chega mesmo.
- **Pausa = encerrar+resume**: medir custo de re-contexto e fidelidade do resume.
- **ccr/versões**: travar versões; o mapa de modelos pode mudar de schema entre releases do ccr.
- **Schema/erros**: usage pode faltar em runs interrompidos; tratar ausência.

## 9. Segurança (repo real)
Container **isolado** (rede controlada; egress allowlist — K); **nunca** commit direto em
`main`/`develop` (branch por issue + PR); **gate humano** no merge/deploy (D7); segredos via vault
(D4), nunca no log; o motor roda com credencial de **app** escopada ao repo (D17/D21).
