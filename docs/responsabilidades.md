# Responsabilidades — o que está MONTADO ⚡

Mapa das peças reais do `src/roboto` com **responsabilidade única** e **fronteiras** ("não faz").
Feito pra ser **criticado**: se uma peça faz coisa demais, ou a fronteira está borrada, é aqui que aparece.
Complementa o esquemático em [`arquitetura.md`](arquitetura.md).

## Princípio: este repo é **IA-first**

O desenvolvedor principal deste repo é um **agente** — humanos definem, revisam e aprovam.
Isso molda o desenho (e este doc):

- **`AGENTS.md` é o contrato** (as regras do repo vivem lá); os docs são escritos pra serem
  **consumidos por agente**: navegáveis, **responsabilidade única** por módulo, fronteiras
  explícitas ("não faz"). Este mapa é o que um agente lê pra saber **onde mexer** sem reler o repo
  inteiro (economia de token, trilha F).
- O processo força **issue-first + review + gate humano**: o agente não coda sem issue completa
  (DoR) nem mergeia sozinho (D28/D7). O humano é o aprovador, não o digitador.
- **Determinismo onde dá** (roteamento, idempotência, gate, recall), **LLM só no julgamento**
  (montar issue, revisar, codar) — pra o agente ser barato, auditável e recuperável.
- Ports/adapters em tudo: o agente troca uma peça (motor, canal, modelo) sem tocar no núcleo.

## Camadas (dependências só apontam "pra baixo")

```
runtime/web            → daemon (ASGI + laços) e console
   │
app/ (fluxos)          → orquestra núcleo + adapters + agents (DETERMINÍSTICO)
   │
agents/ (LLM)          → refiner, review  (julgamento/geração)
   │
orchestrator/ (núcleo) → tipos + Store + outbox  (SEM IO de rede; puro)
   ▲
adapters/              → channels, llm, github, engines  (IO externo atrás de PORTA)
```

Regra: **núcleo não conhece adapter**; app fala com adapter só pela **porta** (Protocol).

## Núcleo (`orchestrator/`) — determinístico, sem rede

| Módulo | Responsabilidade | NÃO faz |
|---|---|---|
| `model.py` | tipos do domínio (Run, GithubEvent, OutboxItem, Session, Interaction, LlmCall, MemoryFact, RunState) | nenhum IO, nenhuma regra de negócio |
| `store.py` | **porta** `Store` + `InMemoryStore`: runs, outbox, sessões, interações, llm_call, memória, cursor; idempotência, claim c/ lease, máquina de estados | não fala com rede/LLM |
| `pg_store.py` | adapter Postgres do `Store` (asyncpg; `FOR UPDATE SKIP LOCKED`; FTS da memória) | não tem lógica de fluxo |
| `core.py` | lógica pura do núcleo (ex.: `publish_outbox`, varredura/lease) | não decide intenção |
| `runner.py` | `RouterPublisher` — roteia um efeito do outbox por `kind` → publisher | não sabe o que é cada efeito |
| `result.py` | `Result/Ok/Err` (sem exceção p/ controle de fluxo) | — |

## Agents (`agents/`) — **único lugar com LLM de julgamento**

| Módulo | Responsabilidade | NÃO faz |
|---|---|---|
| `refiner.py` | pedido → rascunho de issue (`refine`, `converse` entrevistador); parsing determinístico do output | não persiste, não cria issue, não fala com GitHub |
| `review.py` | gate **estrutural** (DoR, sem LLM) + **juiz semântico** + **review de PR** (reviewer≠autor) | não mergeia, não edita |

## App (`app/`) — fluxos (orquestra tudo, determinístico)

| Módulo | Responsabilidade |
|---|---|
| `compose.py` | monta os adapters (gateway, channel, github, router) a partir do `Config` |
| `commands.py` | `parse_command`: intenção **determinística** (help/remember/pick/discuss/list/ideia) — sem LLM |
| `inbound.py` | `dispatch_inbound`: roteia a msg → ação; reply-routing por message_id; aprovação (ok→cria/edita) |
| `refine.py` | refino conversacional (semente→entrevista→proposta), `discuss_issue`, `start_scope`, `propose_issue` |
| `scope.py` | motor lê o repo → rascunho fundamentado (`run_scope` + `process_scope_tick`) |
| `pr_cycle.py` | ciclo issue→motor→git→PR→review→correção (`process_pr_run_tick`); gate de DoR antes de codar |
| `correction.py` | laço implement→review→(repete até max_attempts) |
| `human.py` | `request_human_input` + `handle_reply` (interação humana, D24) |
| `loops.py` | `run_periodic`; `poll_tick` (Telegram: poll→dispatch→responde; cursor) |
| `effects.py` | publishers concretos: `create_issue`, `update_issue`, `telegram_notify`, `telegram_question` |
| `metering.py` | `MeteredGateway` — grava cada chamada de LLM no `llm_call` |
| `git_ops.py` | `SubprocessGit` (branch/commit/push) |
| `engine_loop.py` | `drive_turn` (laço do motor p/ o stub; cria session/interaction) |

## Adapters — IO externo atrás de porta

| Pasta | Porta | Adapter(s) | Responsabilidade |
|---|---|---|---|
| `channels/` | `Channel` | `TelegramChannel` | receber/enviar msg; cursor persistido |
| `llm/` | `ModelGateway`, `Transcriber` | `OpenRouterGateway`, Whisper, stubs | chamar modelo / STT (tier→modelo) |
| `github/` | — | `GithubAppClient`, `webhook` | issues/PR/comment; verify assinatura + opt-in (label/assignee) |
| `engines/` | `CodingEngine` | `ClaudeCodeEngine`, `StubEngine` | motor de código (start/events/respond); matriz de capacidades |

## Web + runtime

| Módulo | Responsabilidade |
|---|---|
| `web/app.py` | `build_app`: console + `/webhook` |
| `web/console.py` | rotas JSON (execuções/detalhe/interações/custos/cancel/retry/terminal) + favicon |
| `web/viewer.py` | página HTML (marca Potter) que consome os endpoints |
| `runtime.py` / `__main__.py` | daemon: ASGI + laços (poll, outbox, sweep, pr_cycle, scope) |
| `config.py` | `Config` + `load_config(env)` |

## Fronteira de determinismo (código × LLM)

- **Código (determinístico):** roteamento de intenção, idempotência, claim/lease, outbox, gate
  estrutural de DoR, reply-routing, recall da memória (FTS), máquina de estados.
- **LLM (julgamento/geração):** refiner (montar issue), juiz semântico, review de PR, motor (codar).
- Output de LLM é **proposta** → parsing determinístico + gate antes de virar efeito (H).

## Fluxos (quem chama quem)

- **Inbound Telegram:** `poll_tick → dispatch_inbound → (command | reply | ideia)` → efeitos no outbox.
- **Scope (issue inteligente):** ideia → run `scope` → `process_scope_tick → run_scope (motor lê repo +
  recall memória) → propose_issue` → aprovação → `create_issue`.
- **Implementar:** `pega #N` → run `impl` → `process_pr_run_tick → run_pr_cycle` (motor→git→PR→review→
  correção) → `verifying`; **merge = humano** (D7).
- **Outbox:** gravar efeito → commit → `publish_outbox` efetua (gravar→commit→efetuar, D9).

## Gaps/dúvidas conhecidas (candidatos à sua crítica)

1. `pr_cycle` e `scope` **duplicam** a lógica de rodar o motor (start/events/session/llm_call) — dá pra extrair.
2. `engine_loop.drive_turn` (stub) e o caminho real (`pr_cycle`) seguem modelos diferentes de sessão.
3. Refino/discussão ainda usam **tier barato** (refiner) — o scope usa o motor forte, mas o chat não.
4. Second brain só **lê** (recall); **não escreve** fatos automaticamente (só via `lembra:`).
5. `terminal` (ttyd) é um shell do container, não a sessão do motor (motor roda via SDK headless).
6. Multi-empresa (D27): hoje 1 processo = 1 tenant; o control-plane (N containers) não está montado.
