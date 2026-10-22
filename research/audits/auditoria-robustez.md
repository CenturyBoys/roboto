# Auditoria de robustez — o que está implementado (2026-10-22)

> 4 auditores adversariais independentes sobre `src/roboto` (núcleo/persistência · motor/ciclos ·
> interação/refino/second-brain · adapters/web/segurança). Objetivo: propor melhorias (não implementado
> ainda). Severidade: **🔴 alta · 🟠 média · 🟡 baixa**. Nenhum código foi alterado nesta auditoria.

## Resumo executivo — os 5 riscos mais sérios

1. **🔴 Segurança: HMAC do webhook falha ABERTO com secret vazio.** `verify_signature` não rejeita
   `secret==""` e o secret não é obrigatório → sem `GITHUB_WEBHOOK_SECRET`, qualquer um forja eventos
   e dispara o fleet (cria runs que codam/abrem PR). (`github/webhook.py:24-28`, `config.py`)
2. **🔴 Integridade: outbox NÃO é exactly-once.** Efetua→marca (ordem invertida), sem dedupe no
   destino, lote aborta em 1 erro, e `pending_effects` sem lock → **efeito duplicado** (PR 2x,
   notificação repetida) sob crash/concorrência. (`orchestrator/core.py:46-57`, `pg_store.py:219`)
3. **🔴 Motor singleton mutável compartilhado** entre o laço de scope e o de PR (ambos a cada 5s):
   `_spec`/`_session_id` se sobrescrevem → corrupção de sessão/medição. (`runtime.py:84-108`)
4. **🔴 Segurança: scope roda com `bypassPermissions`** — "só leitura" é só texto no prompt; o motor
   pode commitar/abrir PR durante a montagem da issue. (`runtime.py:84` + `scope.py`)
5. **🔴 Daemon falha em SILÊNCIO:** `run_periodic` engole toda exceção sem log; token de installation
   do GitHub nunca renova (para de agir após ~1h); cursor do Telegram reprocessa no restart.
   (`loops.py:27-35`, `github/app.py:249`, `channels/telegram.py`)

---

## Segurança 🔐

| # | Sev | Problema | Arquivo | Correção |
|---|---|---|---|---|
| S1 | 🔴 | Webhook HMAC falha aberto (secret vazio) | `github/webhook.py:24` | `if not secret: return False`; exigir secret se webhook exposto |
| S2 | 🔴 | Scope com `bypassPermissions` (só-leitura é só prompt) | `runtime.py:84`,`scope.py:22` | motor dedicado read-only: `permission_mode` leitura + `allowed_tools` (Read/Grep/code-intel, sem Bash/git/Write) |
| S3 | 🟠 | Bearer do console comparado com `!=` (timing attack) | `web/console.py:80` | `hmac.compare_digest` (webhook já usa) |
| S4 | 🟠 | Terminal ttyd sem auth própria (shell bypassPermissions se achar a URL) | `web/console.py:152`, infra | ttyd atrás de auth/proxy; "URL secreta" não é segurança |
| S5 | 🟠 | Opt-in fail-open se label/bot vazios | `github/webhook.py:37` | não tratar "sem filtro" como "reage a tudo"; avisar no boot |
| S6 | 🟠 | Token do bot vaza na URL em msg de erro | `channels/telegram.py:34,126` | redigir token; passar em header, não no path |
| S7 | 🟡 | `assert` em `normalize_event` (sai com `python -O`) | `github/webhook.py:69+` | checagem explícita → `Err("invalid")` |

## Integridade do núcleo (persistência / outbox / estado) ⚙️

| # | Sev | Problema | Arquivo | Correção |
|---|---|---|---|---|
| C1 | 🔴 | Outbox não exactly-once (efetua→marca; lote aborta; sem dedupe) | `core.py:46`, `effects.py` | try/except por item + `attempts`/backoff; **idempotência no destino** via `dedup_key` (handler idempotente) |
| C2 | 🔴 | `pending_effects` sem lock → 2 publishers enviam o mesmo efeito | `pg_store.py:219` | `FOR UPDATE SKIP LOCKED` + claim (`status='sending'`) |
| C3 | 🔴 | Transições de estado não policiadas; sweeper ressuscita run `done` | `store.py:190`,`core.py:60` | compare-and-set (`WHERE ... AND state=$esperado`); sweeper `AND lease_until<now` |
| C4 | 🟠 | Sem unidade de trabalho transacional (estado + outbox não atômicos) | `core.py:38`,`pg_store.py:207` | permitir passar conn/tx: agrupar `set_state`+`enqueue_effect`+`record_llm_call` |
| C5 | 🟠 | `claim_next_queued` (PG) não reconfere estado no UPDATE | `pg_store.py:174` | `UPDATE ... WHERE id=$1 AND state='queued' RETURNING`; tratar `None` |
| C6 | 🟠 | `insert_run_if_absent` pode dar `AttributeError` em corrida (SELECT fora da tx) | `pg_store.py:149` | `ON CONFLICT DO UPDATE ... RETURNING`; INSERT+SELECT na mesma tx |
| C7 | 🟡 | `ABANDONED` nunca usado; índice outbox `(status,created_at)` mas ordena por `id` | `model.py`,`0001` | usar `ABANDONED` p/ timeout; índice `(status,id)` parcial |

## Motor / ciclos (scope · pr_cycle · correção) 🤖

| # | Sev | Problema | Arquivo | Correção |
|---|---|---|---|---|
| E1 | 🔴 | Motor singleton mutável compartilhado scope×PR concorrentes | `runtime.py:84` | **instância por run/tick** (factory), nunca singleton |
| E2 | 🔴 | Sem timeout em `events()`: trava prende run; lease reprocessa não-idempotente | `scope.py:51`,`pr_cycle.py:82` | `asyncio.wait_for` + `interrupt` + `FAILED`; conciliar antes de re-enfileirar |
| E3 | 🔴 | PR ignora evento `FAILED` → commita/abre PR como se tivesse sucesso | `pr_cycle.py:83` | capturar `FAILED`→abortar ciclo; exigir `FINISHED` antes do git |
| E4 | 🟠 | `open_pr` Err → `number=0` e segue (review sobre diff vazio); find Err→PR duplicado | `pr_cycle.py:114` | abortar com `FAILED`; tratar Err de `find_open_pr` ≠ "não existe" |
| E5 | 🟠 | Exceção em `implement/review` deixa run preso em RUNNING, PR aberto | `correction.py:34`,`pr_cycle.py` | `try/except` no tick → `set_state(FAILED)` + notifica + sinaliza PR |
| E6 | 🟠 | `respond`/`interrupt` são no-op no motor real (não dá p/ abortar) | `engines/claude_code.py:90` | migrar p/ `ClaudeSDKClient` (suporta interrupt) |
| E7 | 🟡 | `native_session_id` pode gravar vazio/errado (sem FINISHED / instância compartilhada) | `scope.py:57`,`pr_cycle.py:88` | resolver com E1/E3; avisar quando faltar |

## Robustez operacional (daemon / rede) 📡

| # | Sev | Problema | Arquivo | Correção |
|---|---|---|---|---|
| R1 | 🔴 | `run_periodic` engole TODA exceção sem log → daemon surdo | `loops.py:27` | logar traceback (sem segredo) + contagem/backoff |
| R2 | 🟠 | Installation token do GitHub nunca renova → para após ~1h | `github/app.py:249` | cachear com expiração; em 401 limpar e re-autenticar |
| R3 | 🟠 | Cursor do Telegram reprocessa updates em restart/erro no meio do lote | `telegram.py:61`,`loops.py:82` | persistir cursor incremental; garantir idempotência do inbound |
| R4 | 🟠 | Adapters httpx sem retry/backoff; poll martela em 429 | `telegram/openrouter/stt/github` | backoff exponencial; respeitar `Retry-After`; 4xx≠5xx |
| R5 | 🟠 | Parsing de JSON fora do try → `KeyError`/`JSONDecodeError` cru | `openrouter.py:63`,`telegram.py:58`,`github/app.py:242` | mapear `(KeyError,IndexError,ValueError,JSONDecodeError)`→`Err` |
| R6 | 🟠 | `asyncio.gather` sem `return_exceptions`; crash do uvicorn derruba tudo | `runtime.py:111` | supervisão/restart; handler SIGTERM seta `stop` |
| R7 | 🟡 | Run em WAITING sem TTL/lembrete (preso se humano não responde) | `store.py` sweeper | TTL em WAITING → lembrete/`ABANDONED` |

## Lógica / intenção / gates 🎯

| # | Sev | Problema | Arquivo | Correção |
|---|---|---|---|---|
| L1 | 🔴 | `_ISSUE_REF.search` captura `#N` em qualquer lugar → sequestra ideia nova p/ "discuss" | `commands.py:33` | ancorar ("sobre #N"/"issue #N" no início) ou só quando `#N` isolado |
| L2 | 🟠 | Gate semântico burlável por substring ("não está aprovado"→approved) | `review.py:65-74` | ancorar em `^VEREDITO:\s*(aprovado\|reprovado)`; ausência=reprovado |
| L3 | 🟠 | `check_issue_readiness` só checa substring da seção (vazia passa) | `review.py:51-62` | exigir seção com conteúdo não-vazio |
| L4 | 🟠 | Aprovação "ok" só olha 1ª palavra (falso pos "ok mas muda"; falso neg "por favor cria") | `inbound.py:133` | detectar negação→continua conversa; afirmação com cortesia; "ok mas…"→não cria |
| L5 | 🟡 | `_parse_draft` frágil (cercas de código, lixo vira título) | `refiner.py:45` | regex ancorada + strip de ``` ``` ```; validar seções |

## Second brain (🟡→✅) 🧠

| # | Sev | Problema | Arquivo | Correção |
|---|---|---|---|---|
| G1 | 🔴 | **Sem escrita automática** — só `lembra:` manual → recall quase sempre vazio, valor ~zero | só `inbound.py:180` chama `remember` | gravar fato determinístico nos marcos (issue criada/editada, PR aberto, review) — sem LLM |
| G2 | 🟠 | `recall` InMemory (substring, acento-sensível) ≠ Postgres FTS (stem, sem `unaccent`) | `store.py:409`,`pg_store.py:424` | `unaccent` no tsvector+query; alinhar InMemory ou marcá-lo não-representativo |
| G3 | 🟡 | Sem dedup/`ref`/teto de tamanho (duplicatas inflam recall e prompt) | `inbound.py:181`,`scope.py:43` | dedup por texto normalizado; sintaxe `lembra #N:`; truncar fato no prompt |

## Dívida / qualidade (não-bug, mas pesa) 🧹

- **Q1** Tripla duplicação do "rodar o motor" (scope/pr_cycle/engine_loop) → extrair `run_engine_turn`. (resolve junto com E1/E3/E7)
- **Q2** `InMemoryStore` esconde problemas de concorrência → verde no teste ≠ correto no Postgres; falta teste de concorrência/integração.
- **Q3** `llm_call` perde `provider`; medição hardcoded e não-idempotente por tentativa.

---

## Ordem de ataque sugerida (incrementos; cada um = issue + PR)

1. **Segurança (rápido, risco alto):** S1, S3, S5, S2 (e S4/S6 em seguida). *Fecha os buracos de entrada.*
2. **Integridade do núcleo:** C1+C2 (outbox exactly-once), C3 (estado compare-and-set + sweeper). *O coração.*
3. **Motor seguro e recuperável:** E1 (motor por run), E2+E3 (timeout + FAILED aborta), E4. *Para de corromper/alucinar PR.*
4. **Daemon observável:** R1 (logar), R2 (refresh token), R6 (supervisão). *Deixa de falhar em silêncio.*
5. **Gates/intenção (correção fina):** L1, L2, L3, L4.
6. **Second brain 🟡→✅:** G1 (escrita automática), G2 (unaccent/equivalência), G3.
7. **Dívida:** Q1 (extrair run_engine_turn), Q3, Q2.
