# Arquitetura do Potter — sessão (Claude Code) + interface do Telegram ⚡

Esquemático de como as peças conversam. Dois princípios: **determinismo primeiro** (código no
roteamento; LLM só no julgamento/geração) e **Telegram = conversa, GitHub = registro** (D30).

## Os dois "cérebros"

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│ REFINER / REVIEW         │        │ MOTOR (Claude Code)          │
│ fala com você, vira      │        │ IMPLEMENTA a issue no repo   │
│ ideia→issue, revisa      │        │                              │
│ modelo: OpenRouter/Qwen  │        │ modelo: Qwen via ccr         │
│         (direto)         │        │   (ccr finge Haiku/Sonnet)   │
│ VÊ o Telegram            │        │ NÃO vê o Telegram            │
└─────────────────────────┘        └──────────────────────────────┘
```

O Telegram **não** fala com o Claude Code direto. A ponte é: `Telegram → issue → run → motor`.
Durante um run, se o motor precisa de algo, vira **pergunta no Telegram** (D24) e a resposta volta.

## Interface do Telegram (inbound/outbound)

```
getUpdates ──► TelegramChannel.poll ──► poll_tick ──► dispatch_inbound
                (cursor persistido)                        │
                                                           ▼  parse_command (determinístico)
      ┌───────────────┬───────────────┬──────────────┬───────────────┐
      │ help          │ list          │ pick #N      │ discuss #N     │  (ou: ideia nova)
      │ (guia)        │ (lista issues)│ (trabalhar)  │ (issue existe) │       │
      └───────────────┴───────────────┴──────────────┴───────────────┘       ▼
                                                              refine_to_issue (conversa)
      reply a uma pergunta? ──► handle_reply (roteia pelo message_id, D24)
                                     │
             ┌───────────────────────┼────────────────────────┐
             ▼                        ▼                         ▼
      QUESTION (refiner)       APPROVAL (proposta)       (engine NEEDS_INPUT)
      continua a conversa      ok → cria/edita           responde o motor
```

Saída: tudo que o bot manda passa pelo **outbox** (`telegram_notify` / `telegram_question`). O
`telegram_question` **guarda o message_id** da mensagem enviada — é o que permite rotear o *reply*.

## Gerência de sessão — os 3 IDs (D23)

```
SESSION ⊂ EXECUTION(=run) ⊃ INTERACTION
```

- **execution (= run)**: a unidade de trabalho (uma issue/ideia). Máquina de estados:
  `queued → running → waiting(AWAITING_HUMAN) → verifying → done|failed|abandoned`.
  Tabela `run` (carrega `origin_chat_id` p/ o feedback voltar ao Telegram certo).
- **session**: uma sessão do **motor** (Claude Code) dentro de um run. Guarda o
  `native_session_id` (o id de sessão do próprio Claude Code, p/ `resume`). Tabela `session`.
- **interaction**: uma pergunta/decisão/aprovação ao humano (ou a semente/turnos da conversa de
  refino). Roteada por `channel_message_id` (o reply). Tabela `interaction`.

Fluxo de uma sessão do motor (`engine_loop.drive_turn`):

```
run (running)
  └─ create_session(run, engine) ──► set_native_session(claude_code_session_id)
        └─ engine.events():
             MESSAGE / TOOL_CALL ....................... (trabalho)
             NEEDS_INPUT / NEEDS_APPROVAL → request_human_input → interaction + WAITING
             FINISHED → grava tokens no llm_call; run → verifying
```

> ⚠️ **Gap conhecido:** hoje o caminho real de código (`pega #N` → `run_pr_cycle`) chama
> `engine.start()`/`events()` **direto** e **não grava `session`** — só o `drive_turn` (stub) grava.
> Então o `native_session_id` do Claude Code ainda **não é persistido** nos runs de código reais.

## Onde cada coisa é gravada (Postgres)

| Tabela | O que guarda |
|---|---|
| `run` | execuções (estado, tentativa, lease, origin_chat_id) |
| `run_event` | trilha de transições do run |
| `outbox` | efeitos a efetuar (create_issue/update_issue/telegram_*) — gravar→commit→efetuar |
| `session` | sessões do motor (native_session_id do Claude Code) |
| `interaction` | perguntas/decisões/aprovações + turnos da conversa (roteio por message_id) |
| `llm_call` | medição de token/custo por chamada (refiner + juiz + motor) |
| `channel_cursor` | offset do Telegram (retoma no restart, não reprocessa) |

## Console / viewer (http://host:8090)

| Endpoint | Mostra | Plotado no viewer? |
|---|---|---|
| `/executions` | lista de runs | ✅ |
| `/interactions` | interações pendentes | ✅ |
| `/costs` | tokens/custo (llm_call) | ✅ |
| `/executions/{id}` | **detalhe**: run + **sessões** + **conversa completa** | ❌ (endpoint existe, viewer não abre) |
| `/executions/{id}/terminal` | eventos do motor (stream) | ❌ |
| cancel / retry | ações no run | ❌ |

> **Gap:** o viewer plota as 3 listas, mas **não abre o detalhe de uma execução** (sessões +
> conversa + terminal). Os dados existem na API — falta a tela.
