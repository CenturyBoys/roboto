# Status — pesquisa → implementação ⚡

O que do plano (trilhas + decisões D1–D32) **está no sistema** hoje. Legenda:
**✅ feito** · **🟡 parcial** · **❌ não** (desenhado, não construído).

> Fonte: código em `src/roboto` (PRs #1–#82). Atualizar quando mudar.

## Fundação (D1–D11)

| # | Decisão | Status | Onde / nota |
|---|---|---|---|
| D1 | Stack do roboto | ✅ | Python 3.11 async, ports/adapters, `Result` |
| D2 | Escopo/ordem do MVP | ✅ | loop núcleo (refino→issue→impl→PR→review) |
| D3 | Plataforma de observabilidade | 🟡 | console web + `llm_call`; sem SaaS/dashboard externo |
| D4 | Secrets | 🟡 | env/`.env` (modo PAT); sem Vault/OIDC |
| D5 | Checkpoint/continuidade | ✅ | estado no banco + lease/sweeper (versão leve) |
| D6 | Orçamento token/$ | 🟡 | `llm_call` mede; **sem teto/enforcement** por agente |
| D7 | Gate humano | ✅ | merge humano; propor→ok; nada sem aprovação |
| D8 | Orquestrador + persistência | ✅ | máquina de estados no banco, idempotência+lock, sweeper, PgStore |
| D9 | Outbox exactly-once | ✅ | `outbox` + RouterPublisher + dedup_key |
| D10 | Auditoria `llm_call` | ✅ | tabela + `MeteredGateway` (tokens/custo/tier) |
| D11 | Versão prompt/AGENTS por run | ❌ | `llm_call` não grava versão de prompt/guia |

## Loop núcleo + modelos (A/D/F/I + D12–D16)

| Item | Status | Onde / nota |
|---|---|---|
| A — contratos/DoR/DoD/estados | ✅ | `check_issue_readiness`, `RunState` |
| D — review de PR (reviewer≠autor) | ✅ | `agents/review.py` |
| F — token/ferramentas | ✅ | code-intel/ripgrep, regra de busca, medição |
| I — escada/roteamento de modelos | 🟡 | tiers cheap/judge/frontier (OpenRouter/Qwen); refino ainda barato; mapa op→tier não calibrado |
| D12 issue types/sub-issues/Projects | ❌ | usamos issue + label simples |
| D13 GitHub Spec Kit | ❌ | não adotado |
| D14 skills (onde vivem/versão) | ❌ | sem sistema de skills no fleet |
| D15 canal canônico de aprovação | ✅ | Telegram reply "ok" / merge humano |
| D16 mix de modelos por etapa | ✅ | OpenRouter tiers → Qwen via ccr |

## Operação interativa + motores (N / D20–D26, D28–D32)

| # | Decisão | Status | Onde / nota |
|---|---|---|---|
| D20 | Canais + áudio | ✅ | Telegram + STT (`WhisperTranscriber`) |
| D21 | Bot por empresa / tenant do servidor | 🟡 | 1 bot, tenant por config (não control-plane) |
| D22 | Motores via adapters (contrato) | ✅ | `CodingEngine`, `ClaudeCodeEngine`, `StubEngine` |
| D23 | IDs session/execution/interaction | ✅ | model + store; sessão gravada no scope e pr_cycle |
| D24 | `request_human_input` + reply-routing | ✅ | `app/human.py` |
| D25 | Console web + terminal tmux | ✅ | console + viewer (Potter) + ttyd |
| D26 | Auditoria de execução (eventos) | 🟡 | `EngineEvent`/`run_event`; stream não persistido/plotado |
| D28 | Issue-first + review em todo lugar | ✅ | gate DoR + juiz semântico + escada de review |
| D29 | Opt-in (label/assignee) | ✅ | `github/webhook.py` |
| D30 | Telegram conversa × issue registro | ✅ | propor→ok, editar com ok + comentário de trilha |
| D31 | Engine-scoped (motor monta a issue) | ✅ | `app/scope.py` |
| D32 | Second brain (fatos + FTS) | 🟡 | recall + FTS feitos; **escrita automática + export `.md` faltam** |

## Multi-empresa + temas ainda abertos (D17–D19, D27, trilhas B/C/G/H/J/K/L)

| Item | Status | Onde / nota |
|---|---|---|
| D17 tenancy/Docker image | 🟡 | 1 imagem, 1 tenant/processo, `ROBOTO_REPOS` |
| D18 agente sênior persistente | ❌ | não |
| D19 acesso leitura a dados/APIs da empresa | ❌ | só o repo |
| D27 control-plane multi-empresa (fleet manager) | ❌ | só desenho |
| B — gatilhos ambiente/schedule | ❌ | só reativo (webhook/poll) |
| C — skills (progressive disclosure) | ❌ | não |
| G — memória: write automático + `.md`/git | 🟡 | só recall por ora |
| H — evals/golden set + sandbox forte (gVisor/Firecracker) | ❌ | só gates + `Result` + lease |
| J — merge-queue / test-impact | ❌ | só CI tier-1 |
| K — runtime efêmero | ✅ | Docker/compose; isolamento forte ❌ |
| L — baseline de custo / teto | 🟡 | mede (`llm_call`); sem baseline/teto |

## Resumo
- **Pronto (✅):** o **loop interativo de ponta a ponta** — ideia/issue (incl. motor escaneando o repo)
  → proposta→ok → implementação → PR → review → gate humano; Telegram + console + motores + auditoria
  de token + outbox/idempotência/recuperação.
- **Parcial (🟡):** second brain (só lê), observabilidade/secrets/orçamento, tenancy (1 por processo), roteamento fino de modelo.
- **Falta (❌):** control-plane multi-empresa, skills, gatilhos de ambiente, evals/sandbox forte,
  merge-queue/test-impact, versão de prompt por run, Spec Kit, agente sênior/acesso a dados da empresa.
