# PoC — motor vivo contra repo real (plano em `research/N3-poc-plano.md`)

Tudo isolado num container: build/test do repo-alvo (Playwright), `roboto` (daemon), **Claude Code**
backeado por **OpenRouter/Qwen** via **claude-code-router** (qwen3-coder big / qwen-2.5 small).

## Fase 0 — encanamento (sem secrets, sem tocar o GitHub)
```bash
./poc/phase0.sh          # builda, sobe Postgres, checa ferramentas, roda o smoke do loop
KEEP=1 ./poc/phase0.sh   # mantém os containers de pé no fim
```
Prova: imagem builda · Postgres sobe · ferramentas presentes (node/pnpm/python/claude/ccr/playwright)
· `roboto` importa · o laço **claim→motor** roda com `StubEngine` (run → `VERIFYING`), via `poc/smoke.py`.
**Não precisa de `.env.poc`** nem gasta token.

## Fase 1 — motor vivo
```bash
cp poc/.env.poc.example poc/.env.poc   # preencha os secrets (gitignored); ROBOTO_ENGINE=claude_code
docker compose -f poc/compose.poc.yml --env-file poc/.env.poc up --build
```

## Fases (resumo)
- **Fase 0 — encanamento** (`ROBOTO_ENGINE=stub`): `./poc/phase0.sh`. Valida o container **sem gastar
  token nem tocar o GitHub**.
- **Fase 1 — motor vivo** (`ROBOTO_ENGINE=claude_code`): requer o `ClaudeCodeEngine` (próximo PR,
  N3 gap#2). Issue pequena → branch → PR → **CI do jo-ken-po** → review. Gate humano no merge.

## Validado (Fase 0, 2026-10-20)
- Imagem **playwright:v1.48.0-noble** (Python 3.12 + venv). Claude Code 2.1.197, ccr 2.0.0, Playwright 1.64.1.
- `claude-agent-sdk==0.2.168` (no extra `engine`); ccr v2 config com `transformer`+`NON_INTERACTIVE_MODE`, porta 3456.
- **Resta confirmar ao vivo (Fase 1):** IDs exatos dos modelos Qwen no OpenRouter (valide em
  openrouter.ai/models) e o comportamento de aprovação/retomada do motor.

## Segurança
Container isolado; **nunca** commit direto em `main`/`develop` (branch+PR); gate humano no merge;
segredos só via `.env.poc`/vault (nunca no log); GitHub App escopado ao repo-alvo.
