# Roteiro de teste pela UI (cockpit) — stack do PoC contra o repo-alvo

> Arquivo **local** (gitignored na prática — não commitar). Testa as features da branch
> `feat/trilhas-ab-execucao` dirigindo o cockpit, contra `arenavalendo/main`.

## Subir
```bash
docker compose -f poc/compose.poc.yml --env-file poc/.env.poc up --build
```
- Console (cockpit): **http://localhost:8090** — cole o `CONSOLE_TOKEN` do `poc/.env.poc`.
- Terminal web (ttyd+tmux): **http://localhost:7681**
- O container clona o repo em `/work/arenavalendo/main`, sobe o ccr (→ OpenRouter) e o motor
  `claude_code`. DB é efêmero (sem volume) → `poc/migrate.py` aplica TODAS as migrations (incl.
  0009 dead-letter/backoff) a cada subida.

## Passos

| # | Passo na UI | O que prova |
|---|---|---|
| 1 | Colar `CONSOLE_TOKEN` → aba **Issues** lista issues do arenavalendo | GitHub RO + token |
| 2 | Escolher issue → **Refino** (motor lê o repo, propõe DoR) → **📝 Aplicar** | refino engine-scoped + second brain + **code-intel v0.9.0** |
| 3 | **Implementar** a issue → **Execuções** (estado) + feed SSE + **Custos** | ciclo PR→`develop`, **verify shift-left** (code-intel/tsgo anota no PR), right-sizing de modelo |
| 4 | Aba **Revisar PR** → nº do PR | review (autor≠revisor), **DoR exige critério verificável**, achados do verify injetados |
| 5 | Disparar a **mesma issue 2×** | **concurrency-lock por (tenant,issue)** → 1 run só |
| 6 | Forçar uma falha → ver em `/dead-letter` → **replay** | **retry/backoff + dead-letter** (migration 0009) |
| 7 | Se o motor perguntar → aba **Interações pendentes** responder | HITL (`request_human_input`) |

## O que NÃO dá pra testar só pela UI local
- **Anti-loop por sender** (webhook): o GitHub não entrega webhook pro localhost. Precisa de túnel
  (smee.io/ngrok) + `GITHUB_WEBHOOK_SECRET` + `ROBOTO_BOT_LOGIN` setado (hoje ausente no `.env.poc`).

## Notas
- Gate humano: o fleet abre PR em `develop`, **nunca** mergeia sozinho.
- code-intel pinado em **v0.9.0** no `poc/Dockerfile` (`IDE_CC_VERSION`).
- Smoke isolado do motor (sem Postgres/Telegram): definir `POC_TASK` no `.env.poc` (ver `TUTORIAL.md §5.1`).
