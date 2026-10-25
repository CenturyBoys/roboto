# Trilha O · Interface de gerenciamento — Telegram vs. console web vs. adotar ferramenta

> **Origem:** insatisfação do dono (2026-10-22) com o **Telegram para GERÊNCIA** ("vai ficando
> confuso"). Pergunta: adotamos uma das ferramentas de orquestração de agentes que existem hoje
> (Orca, Conductor, Emdash, Superset, Synara, Paseo, Agentastic), ou roubamos ideias e evoluímos o
> **nosso** console? Esta trilha fecha a pergunta em aberto da **Trilha N §7.3** ("stack do console:
> FastAPI+HTMX vs SPA").
>
> **Disciplina de fontes:** quase tudo abaixo vem de landing page / README / changelog / Show HN —
> **fonte de vendor, indicativa**. Onde a própria ferramenta admite uma limitação (ex.: HN dos
> fundadores), está marcado. Nenhum número de tração/stars/preço foi verificado de forma independente.

## 1. Pergunta

O Telegram é ótimo como **conversa** (refino, 1 pergunta por vez, aprovar com `ok`), mas ruim como
**painel de gerência**: chat é linear e serial, e acompanhar **N execuções em paralelo** (qual está
rodando, qual travou esperando humano, quanto cada uma gastou, qual o diff) vira ruído. Qual é a
interface de **gerência** certa — e dá pra comprar pronta?

## 2. Estado da arte — o que o mercado construiu (out/2026)

Pesquisamos 7 ferramentas da categoria "orquestrador/IDE de agentes de coding em paralelo". **O
achado mais importante é que elas são todas a MESMA coisa, e NÃO são o que nós somos:**

> **Padrão único da categoria:** app **desktop** (quase sempre macOS), **single-user**,
> **local-first**, **humano-no-volante**, que roda **N agentes CLI em paralelo**, cada tarefa em seu
> **git worktree**, com **diff viewer + terminal + PR** embutidos e **BYO-key** (não revendem
> inferência). O "registro" de estado vive **na máquina** (SQLite/daemon local), não no GitHub.

Três coisas que **nenhuma** delas faz bem — e que são o nosso núcleo:

1. **Processo/governança imposto.** Nenhuma tem **gate de review por agente ≠ autor**, **DoR/DoD**,
   ou **políticas que bloqueiam** o agente por regra. No máximo há *encadeamento* ("implement →
   review → document") como receita/convenção, não como gate duro. Superset admite no HN:
   *"no built-in pipeline or gate definitions"*.
2. **GitHub como registro canônico.** Para elas, a issue é **input**; a verdade do estado é **local**.
   Para nós, a issue **é o registro** (D30) e o gate canônico é o GitHub (D15).
3. **Observabilidade de custo/token agregada.** Quase todas mostram quota/rate-limit da assinatura e
   contexto por sessão, mas **custo/token agregado por issue/execução/fleet é ausente ou só
   roadmap** (Synara tem RFC aberto p/ `cost`; Paseo admite faltar "sumário por projeto"). É
   justamente o nosso objetivo de 1ª classe (economia de token).

### Comparativo

| Ferramenta | Licença | Plataforma | Motores | Custo/token | Processo/gates | Fit p/ adoção |
|---|---|---|---|---|---|---|
| **Orca** (onorca.dev) | **MIT** | Desktop + mobile + `orca serve` | ~27 CLIs | uso/rate-limit (não $/token fino) | **Camada de orquestração** (Run/Task/Dispatch/Message/**Gate**), genérica, sem papel | ❌ adotar · ✅✅ roubar |
| **Emdash** (generalaction) | **Apache-2.0** | Electron desktop | ~9–23 CLIs | **não tem** | só lifecycle scripts (`.emdash.json`) | ❌ adotar · ✅ roubar (ADRs) |
| **Paseo** (paseo.sh) | **Apache-2.0** | Daemon + Desktop/Web/**iOS/Android**/CLI | ~40 (ACP) | context meter/sessão; sem agregado | Skills handoff/committee/advisor (convenção) | ❌ adotar · ✅✅ roubar |
| **Synara** (Emanuele-web04) | **MIT** | Desktop + `synara-server`+web | ~11 CLIs | tokens sim, **$ é RFC** | Plan mode, `/review`, checkpoints (opcionais) | ❌ adotar · ✅✅ roubar |
| **Superset** (superset.sh) | ELv2 (source-avail.) | Desktop mac + mobile + CLI/SDK/MCP | 20+ CLIs | **tem** "Usage" (quota+$/token) | Automations + chaining; **sem gates** (admitido) | ❌ adotar · ✅ roubar |
| **Conductor** (conductor.build) | Closed (SaaS) | **Mac app** + iOS + cloud | CC/Codex/Cursor/OpenCode | parcial/experimental | Plan mode, tool approval, **pre-merge checklist** | ❌ adotar · ✅ roubar |
| **Agentastic** (agentastic.ai) | Closed (free) | **macOS** + iPhone | ~55 "defs" | **não tem** | pipeline cross-provider (padrão de uso) | ❌ adotar · ✅ roubar |

> Correções de identidade (os links tinham domínio/repo errado): Conductor = **conductor.build**
> (Melty Labs), não `conductor.is`; Paseo = **paseo.sh / getpaseo**, não `paseo.ai`; Synara =
> **github.com/Emanuele-web04/synara** (o `SynaraAI/synara` dá 404); Emdash = **generalaction/emdash**.

## 3. Por que NÃO adotar nenhuma como plataforma

Adotar qualquer uma **inverteria nossos três eixos**:

- **Desktop/single-user ↔ nós somos headless/server-side/multi-tenant.** Elas assumem alguém
  olhando a janela do Mac. Nosso fleet roda em container efêmero, 1-por-task, com estado durável
  fora do container (K), dirigido por orquestrador. (Orca/Paseo/Synara têm modo server, mas é
  afluente, não o rio.)
- **Estado local ↔ GitHub canônico (D15/D30).** O registro delas é SQLite/daemon local; o nosso é
  a issue/PR no GitHub.
- **Sem processo imposto ↔ processo+gate é o nosso produto.** Nossa tese não é "rode N agentes" — é
  **processos + agentes que garantem qualidade** (issue-first, DoR/DoD, gate de review por agente
  diferente do autor, determinismo primeiro). Comprar uma delas nos daria a casca (UI) e nos tiraria
  o miolo (governança).

**Conclusão:** essas ferramentas são a **referência de UX/HITL** que nos faltava — não a base.

## 4. O que roubar — mapeado para a nossa arquitetura

Priorizado por valor × baixo custo de token/implementação. (Orca MIT, Emdash/Paseo Apache-2.0,
Synara MIT → **código legível**; Superset ELv2 cuidado; Conductor/Agentastic fechadas.)

1. **Painel de N execuções com estado + "inbox do que precisa de você".** O consenso de UX contra o
   caos: dashboard com *pills* `running/waiting/verifying/done/failed` e uma fila priorizada de HITL
   (Agentastic: atalho "pula pro próximo agente que te espera"; Superset: `working/blocked/awaiting-review`).
   → **Onde entra:** vira o `/` e o `/interactions` do nosso console (`web/console.py`); mapeia direto
   na máquina de estados do `run` e na tabela `interaction`. É a cura concreta pra dor do Telegram.
2. **Diff com comentário inline que volta ao agente como instrução.** Orca, Conductor, Synara (botão
   "Fix" agrupa comentários num prompt). É o **gate de review (D28) virado interativo** — o humano
   comenta, o agente corrige, sem sair da tela. → novo endpoint de review no console.
3. **Checklist de pré-merge bloqueante = DoD** (Conductor). Nosso DoD deixa de ser texto na issue e
   vira **checklist que trava o merge** — determinismo primeiro, política decide (H).
4. **Contrato de orquestração Run/Task/Dispatch/Message/Gate** (Orca, MIT — **ler o código**): inbox
   FIFO, `worker_done` idempotente, `dispatch-authority` (evita retomar retry velho), `gate-create`/
   `gate-resolve`. Valida/espelha nossos IDs **session/execution/interaction** (D23) e o **outbox** (D9).
5. **ADRs de ciclo de vida de workspace** (Emdash, Apache-2.0 — **ler**): `registry-single-writer`,
   `tombstone-and-reconcile-deletion`, `cancellation-is-best-effort`. É exatamente o que precisamos
   p/ dirigir motores em worktrees sem corrida de estado — insumo direto p/ **D22 (EngineAdapter)**.
6. **handoff / committee / advisor** (Paseo) como **primitivas de processo**: briefing self-contained
   com *Acceptance Criteria* + um revisor **que não pode editar código** = formalização limpa do
   nosso **review por agente ≠ autor**. `committee` (duas análises independentes) ≈ segunda opinião.
7. **Observabilidade de custo/token como vantagem nossa, não paridade.** Todas são fracas aqui; nós
   já temos `/costs` (tabela `llm_call`). → ir além: **agregado por issue / por execução / por fleet**,
   com teto e alerta (Trilha L). Isso é um diferencial de fato, não um "me-too".
8. **Provider handoff com contexto preservado + Agent Gateway (MCP)** (Synara, MIT): trocar de motor
   no meio preservando contexto, e um surface MCP app-owned com escopo revogável p/ agentes dirigirem
   tasks. Insumo p/ o contrato **EngineAdapter** (D22) e p/ expor ações do fleet com segurança.
9. **Daemon mantém sessão viva com a UI fechada** (Superset/Paseo). Nós **já ganhamos isso de graça**
   por sermos server-side — é um ponto onde nossa arquitetura já é superior ao desktop.
10. **Companion mobile de aprovação** (Paseo nativo; Orca/Conductor/Agentastic): valida **manter o
    Telegram** — como *push + aprovação móvel*, não como painel de gerência.

## 5. Recomendação

**Não adotar nenhuma. Reposicionar o Telegram e promover o console web a cockpit de gerência.**

- **Telegram re-escopado** → *conversa + push + aprovação móvel* (o que os companions mobile fazem
  bem). Refino de issue, pergunta do motor, `ok` de aprovação continuam lá. **Tiramos dele o papel
  de "acompanhar o fleet"** — é aí que ele confunde.
- **Console web = cockpit de gerência** (evolui `web/console.py`, que hoje é viewer read-mostly):
  painel de execuções com estado ao vivo, inbox de HITL priorizada, diff-com-comentário→agente,
  painel de custo/token **agregado**, checklist de DoD bloqueante. Nada disso exige adotar ferramenta
  de terceiro — exige roubar os padrões do §4 e plugar no backend que já temos (canais são adapters, D20).
- **Stack do console (fecha a pergunta da Trilha N §7.3): server-render + HTMX/SSE, não SPA.**
  Justificativa: backend já é Python/async (Starlette); live-update de um dashboard é o caso-modelo
  de SSE+HTMX; mantém determinismo e **baixo custo de manutenção/token**; evita o peso Electron/SPA
  que torna as ferramentas de mesa pesadas. Reavaliar SPA **só** se o diff-com-comentário interativo
  provar precisar — e, mesmo aí, como ilha, não reescrita.

> Em uma linha: **elas nos deram o mapa da UI de gerência que faltava; o diferencial (processo+gate+
> GitHub canônico+custo agregado) continua sendo nosso e é o que nenhuma entrega.**

## 6. Impacto em token

- O cockpit web é **determinístico** (lê o mesmo store; render server-side) → custo de token ~zero,
  igual ao Telegram-notificador (M).
- **Ganho indireto grande:** gerência clara reduz re-trabalho (humano vê cedo o que travou/desviou →
  aborta antes de queimar tokens) e o **painel de custo agregado** torna a economia mensurável por
  issue/execução — o que o mercado inteiro ainda não entrega.

## 7. Desenho do cockpit (PWA) — catálogo de recursos (decisão do dono, 2026-10-22)

Dono aprovou a direção e refinou: **PWA instalável** (acessível na máquina / por VPN tipo Tailscale),
que **visualiza as execuções** e permite **conversar com a sessão do Claude ali mesmo** (como no
Orca). O Telegram **sai de "painel"** (ficou disperso) e fica só como *conversa/push móvel*.
Isso **supera a pergunta da Trilha N §7.3** (stack do console).

### 7.1 O que o backend JÁ sustenta vs. o que FALTA

Auditado no código (`web/console.py`, `app/engine_loop.py`, `app/pr_cycle.py`, `app/human.py`,
`engines/claude_code.py`, `engines/port.py`):

| Recurso do cockpit | Estado | O que falta (se falta) |
|---|---|---|
| Listar execuções + estado (pills `running/waiting/verifying/done/failed`) | ✅ já temos | só UI melhor (`/executions`) |
| Detalhe: run + sessões + interações | ✅ já temos | idem (`/executions/{id}`) |
| Custo/token por execução | ✅ já temos (`llm_call`/`/costs`) | **agregar** por issue/fleet (L) |
| Cancel / retry por execução | ✅ já temos | expor como botão no PWA |
| **Terminal vivo da sessão (ttyd+tmux)** | ✅ feito | embutido no PWA (iframe) + **anexo por-run** (`COPILOT_MODE=tmux`, Fatia 7) |
| Inbox priorizada de HITL ("o que precisa de você") | ✅ feito | responde pelo front (`/interactions/{id}/answer`); ordenar por urgência = refinamento |
| Feed legível "o que o Claude está fazendo" (mensagens/tool-calls) | ✅ feito | `session_event` + **SSE** (`/executions/{id}/events`); painel no detalhe + chat |
| Responder pergunta do motor pelo front (sem Telegram) | ✅ feito | inbox de interações responde pelo cockpit (mesmo `answer_interaction` do Telegram) |
| **Conversar/steer a sessão a qualquer momento** (chat bonito) | ✅ feito | `ClaudeSDKClient` + `SessionHub`; chat estilo mensageiro; validado ao vivo (Fatia 5) |
| Aprovação por ação (allow/deny de ferramenta) | 🟡 parcial | `can_use_tool`→Future do hub encanado; o co-piloto usa `bypassPermissions` (leitura fluida) por ora |
| Diff do PR no front (+ comentário→agente) | ✅ feito (UI) | diff no detalhe (`/executions/{id}/diff`); comentário→agente ainda pendente (gate §4.2) |
| PWA instalável + VPN | ✅ feito (PWA) | `manifest.json` + service worker instaláveis; VPN/HTTPS = infra (K), fora do app |

### 7.2 Dois modos de operação (decisão que trava o escopo)

- **Modo A — Torre de controle** (observa + responde *quando o motor pergunta*): inbox HITL + feed
  read-only + terminal embutido p/ os casos crus. **Casa com o ciclo autônomo atual e o determinismo
  primeiro**, entrega a cura da dor do Telegram com **pouco** backend novo.
- **Modo B — Co-piloto** (conversa/steer a sessão a *qualquer* momento, estilo Orca): exige
  `ClaudeSDKClient` bidirecional + transporte WebSocket + `respond()`/`interrupt()` reais. Mais
  poderoso e é o "feeling Orca", mas muda o motor de `query()`→client e tem **tensão com autonomia/
  token** (sessão fica viva esperando humano).

> **Recomendação:** começar por **A** — e o **terminal embutido já entrega um "falar com a sessão"
> cru imediato** enquanto B (o chat bonito) espera o PoC do `ClaudeSDKClient`. Evolui A→B sem jogar
> nada fora.

### 7.3 Stack (fecha a §7.3 da Trilha N)

**App-shell PWA servido pelo próprio Starlette** (não SPA pesada): `manifest` + service worker
(instalável/offline-shell), **SSE** para os feeds ao vivo (execuções, event feed), **WebSocket só
para o chat do Modo B**. Auth = bearer que já existe (`CONSOLE_TOKEN`), isolamento por tenant (D17)
que já existe. Interatividade localizada com ilhas de JS (ou HTMX) onde precisar — sem framework SPA
grande (determinismo + baixo custo de manutenção/token).

### 7.4 Ordem de construção (fatias finas, cada uma entrega valor)

1. ✅ **PWA shell + terminal embutido** *(feito 2026-10-22)* — cockpit **React + TS + Tailwind +
   shadcn** em `web/ui/`, instalável (manifest+SW), responsivo **mobile-first** (cards no celular,
   tabela em `sm+`), com lista de execuções (auto-refresh), detalhe (sessões/interações), custos,
   cancel/retry e **terminal (ttyd) embutido em iframe**. Builda para `src/roboto/web/static/` e é
   servido pelo Starlette, com **fallback no viewer legado** quando não há build. CI ganhou job de
   front (typecheck+vitest+build); Dockerfile multistage (imagem ~162 MB, não-root).

   **Config no banco + modo setup** *(feito 2026-10-22)* — a config operacional vive em `app_config`
   (migração `0006`); o `.env` só **semeia** o banco no boot (fonte única). Sem config obrigatória, o
   daemon sobe em **modo setup** (não morre) servindo o cockpit + `/setup` (atrás do `CONSOLE_TOKEN`)
   pra preencher pela tela; ao completar, recarrega e sobe os laços. Bootstrap só por env:
   `DATABASE_URL` + `CONSOLE_TOKEN` (o compose já injeta os dois → `docker compose up` sem `.env`
   cai direto no setup). Prod pode seguir o ansible-vault (D4). Validado ponta-a-ponta via Docker.
2. ✅ **Feed legível ao vivo** *(feito 2026-10-22)* — eventos do motor (MESSAGE/TOOL_CALL) persistidos
   em `session_event` (migração `0007`), gravados no caminho real (`run_pr_cycle`) e no `drive_turn`;
   **SSE** em `GET /executions/{id}/events` (backlog + live, bearer + isolamento). No front, painel
   "Feed ao vivo" no detalhe consome via fetch-stream (EventSource não manda Authorization). *Ver o
   que o Claude faz sem terminal cru.* Validado sob uvicorn real (curl `-N`).
3. ✅ **HITL no front** *(feito 2026-10-22)* — inbox de interações pendentes com resposta pelo
   cockpit: decisão (botões por opção) ou pergunta aberta (texto). Endpoint
   `POST /interactions/{id}/answer` (bearer + isolamento D17) usa o **mesmo `answer_interaction`** do
   reply do Telegram (1ª resposta válida vence, §6). *Responder o motor sem Telegram.*
   **Pendente (quando a interatividade do motor entrar):** unificar `run_pr_cycle` com o protocolo do
   `drive_turn` pra que as perguntas do caminho real cheguem à inbox, e o **resume** pós-resposta
   (hoje a resposta é registrada como no Telegram; retomar é do motor — D22, casa com a Fatia 5).
4. ✅ **Custo agregado + diff** *(feito 2026-10-22)* — `/costs` agrega **por execução** (`by_execution`)
   e o detalhe mostra o **custo da execução** (`cost_for_execution`). Diff do PR persistido por
   execução (`execution_pr`, migração `0008`) pelo ciclo de review; `GET /executions/{id}/diff` e
   painel no detalhe (linhas +/−/@@ coloridas). **Pendente:** comentário-no-diff→agente (gate de
   review interativo) fica pra depois da interatividade do motor (casa com a Fatia 5).
5. ✅ **Co-piloto** *(feito 2026-10-23; validado ao vivo c/ modelo)* — `SessionHub` (registro em
   processo de sessões vivas): fila de **steer** + **`Future` de aprovação** + **interrupt** + **end**.
   Console: `POST /executions/{id}/message` (steer OU inicia a sessão sob demanda), `/interrupt`,
   `/end`. Front: **chat estilo mensageiro** (`Chat.tsx`) — suas bolhas de um lado, o motor do outro
   (markdown), tool-calls como pills; toggle resumido/detalhado; interromper/encerrar. **Driver real
   plugado no `runtime`** (não mais só PoC): `app/copilot.py` (`ClaudeSDKClient`) com
   `permission_mode=bypassPermissions` (leitura fluida, sem travar em aprovação), **vigia concorrente**
   que corta o motor NO INSTANTE do interromper/encerrar (prioridade máxima), **resume** da sessão
   nativa com **fallback** p/ sessão nova (rebuild apaga o disco), e **modelo fixo** (`qwen/qwen3-coder`).
   **Dois drivers por `COPILOT_MODE`:** `sdk` (feed estruturado) e `tmux` (ver Fatia 7). Refino é
   **read-only** (bloqueia Write/Edit/Bash). Validado ao vivo contra `arenavalendo/main`.
6. ✅ **Refino no cockpit + aplicar na issue** *(feito 2026-10-23)* — pedido do dono: fazer o ciclo da issue pela UI,
   não só pelo Telegram. **Feito:** lista de **issues abertas** no cockpit (`GET /issues` via
   `GithubAppClient.list_open_issues_rich` — só `state=open`, **closed/PR nunca entram**; com **labels**;
   aba "Issues" com **filtro** por nº/título/label; repo do `default_repo`/`?repo=`).
   **Também feito:** issue **clicável** → painel com corpo + **DoR** (`check_issue_readiness`,
   `GET /issues/{n}`) e **conversa de refino** (`POST /issues/{n}/refine` → `converse` do refiner via
   OpenRouter; stateless, o front manda o transcript) que pergunta até propor um **rascunho** + DoR.
   **Refino ENGINE-SCOPED (D31, estágio C):** botão **"Refinar com o motor"** (`POST /issues/{n}/
   refine-engine`) enfileira um run `agent='refine'`; `process_refine_tick` injeta o corpo da issue e
   roda o **motor (Claude Code)** que **LÊ o repo** (Read/Grep) e propõe a issue fundamentada — os
   eventos viram **feed ao vivo**. Resolve o "chat cego": o agente lê o código de verdade. Infra do
   motor vive no `poc/` (ccr→OpenRouter/Qwen); o `poc/Dockerfile` agora serve o cockpit (SPA). Validado
   ao vivo (run_engine: tool Read + resumo do repo).
   **Aplicar na issue** *(feito 2026-10-23)*: o refino emite o corpo final entre marcadores
   (`===ISSUE-INICIO===`/`===ISSUE-FIM===`); `GET /executions/{id}/proposal` extrai o **corpo limpo**
   (âncora no miolo, robusto à quebra dos `===`) e o botão **"📝 Aplicar na issue"** abre textarea
   editável → `POST /executions/{id}/apply` chama `update_issue` + comentário de trilha (D30: só com OK
   humano). Ciclo da issue fechado pela UI (listar → refinar lendo o repo → aplicar no GitHub).
7. ✅ **Terminal real do motor (tmux por-run)** *(feito 2026-10-23)* — `COPILOT_MODE=tmux`: o
   co-piloto roda o **Claude Code CLI numa tmux por-run** (`roboto-run-<id>`); o botão **Terminal**
   anexa nela (`ttyd -a`, `?arg=roboto-run-<id>`) e você **vê/opera a sessão REAL**. Chat injeta via
   `tmux send-keys` (chat manda, terminal espelha); feed ← **transcript JSONL** do CLI. Entrypoint
   pré-semeia onboarding/trust/skip-bypass; launch sem `ANTHROPIC_API_KEY` abre direto no REPL.
   `sdk` segue de fallback. `app/tmux_copilot.py`. Validado ponta-a-ponta no container.

## 8. Perguntas em aberto (para o dono)

1. ✅ **RESOLVIDO** (2026-10-22) — direção aprovada: **não adotar** ferramenta pronta; construir o
   **cockpit PWA** (React+TS+Tailwind, não HTMX) + re-escopo do Telegram. Fatias 1–7 entregues.
2. ✅ **RESOLVIDO** — todos os três entregues: **(a)** inbox de HITL, **(b)** diff no front (o
   comentário→agente ainda falta), **(c)** custo agregado por execução. Ordem seguida ~ a → c → b.
3. Vale eu **ler o código** de Orca (contrato de orquestração) e os **ADRs do Emdash** (lifecycle de
   workspace) e trazer um resumo acionável p/ D22/D23/D24 — já, ou depois de aprovar a direção?

---

### Fontes (todas indicativas — vendor/landing/HN, salvo nota)

- Orca: https://www.onorca.dev/docs/cli/orchestration · repo https://github.com/stablyai/orca
- Emdash: https://github.com/generalaction/emdash · ADRs https://github.com/generalaction/emdash/tree/main/docs/adr
- Paseo: https://paseo.sh/ · https://github.com/getpaseo/paseo · skills https://paseo.sh/docs/skills
- Synara: https://github.com/Emanuele-web04/synara · RFC custo https://github.com/Emanuele-web04/synara/issues/1251
- Superset: https://superset.sh/ · https://docs.superset.sh/overview · Launch HN https://news.ycombinator.com/item?id=48236770
- Conductor: https://www.conductor.build/changelog · Show HN https://news.ycombinator.com/item?id=44594584
- Agentastic: https://agentastic.ai/ · Show HN https://news.ycombinator.com/item?id=46501758
- Diretórios de categoria: https://openalternative.co/blog/best-ai-coding-agent-orchestrators · https://agentmgmt.dev/
