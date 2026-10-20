# PoC — motor vivo contra repo real (plano em `research/N3-poc-plano.md`)

Tudo isolado num container: build/test do repo-alvo (Playwright), `roboto` (daemon), **Claude Code**
backeado por **OpenRouter/Qwen** via **claude-code-router** (qwen3-coder big / qwen-2.5 small).

## Como rodar
```bash
cp poc/.env.poc.example poc/.env.poc   # preencha os secrets (gitignored)
docker compose -f poc/compose.poc.yml --env-file poc/.env.poc up --build
```

## Fases
- **Fase 0 — encanamento** (`ROBOTO_ENGINE=stub`): builda, sobe Postgres+daemon, clona o alvo,
  `StubEngine` percorre claim→drive; valida o container (pnpm/Playwright disponíveis) **sem gastar
  token nem tocar o GitHub**.
- **Fase 1 — motor vivo** (`ROBOTO_ENGINE=claude_code`): requer o `ClaudeCodeEngine` (próximo PR,
  N3 gap#2). Issue pequena → branch → PR → **CI do jo-ken-po** → review. Gate humano no merge.

## A validar no 1º build (não exercitado sem rede/segredos)
- Tag da imagem Playwright; nomes/versões de `@anthropic-ai/claude-code` e `@musistudio/claude-code-router`.
- Porta do `ccr` (assumido 3456) e formato de `ccr.config.json` da versão instalada.
- `pip install --break-system-packages` na imagem base.
- IDs exatos dos modelos Qwen no OpenRouter (`qwen/qwen3-coder`, `qwen/qwen-2.5-72b-instruct`).

## Segurança
Container isolado; **nunca** commit direto em `main`/`develop` (branch+PR); gate humano no merge;
segredos só via `.env.poc`/vault (nunca no log); GitHub App escopado ao repo-alvo.
