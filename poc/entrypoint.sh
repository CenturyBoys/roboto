#!/usr/bin/env bash
# Entrypoint do PoC: sobe o claude-code-router (-> OpenRouter/Qwen), clona o repo-alvo e
# roda o daemon roboto. Fase 0: ROBOTO_ENGINE=stub (encanamento). Fase 1: claude_code.
set -euo pipefail

: "${OPENROUTER_API_KEY:?defina OPENROUTER_API_KEY no .env.poc}"
: "${TARGET_REPO_URL:?defina TARGET_REPO_URL (ex.: git@github.com:arenavalendo/main.git)}"

# 1) config do router a partir do template (injeta a chave do OpenRouter)
mkdir -p "$HOME/.claude-code-router"
envsubst < /opt/roboto/poc/ccr.config.json > "$HOME/.claude-code-router/config.json"

# 2) sobe o ccr (porta 3456) e espera ficar pronto; aponta o Claude Code para ele
ccr start >/tmp/ccr.log 2>&1 &
for _ in $(seq 1 15); do ccr status >/dev/null 2>&1 && break; sleep 1; done
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:3456}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-sk-ccr-noop}"      # ccr ignora; chave real = OPENROUTER
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"  # redundância (bearer)

# 3) checkout do repo-alvo (o motor roda com cwd neste diretório)
#    repo privado: use GITHUB_CLONE_TOKEN (PAT fine-grained no PoC, ou token de instalação do App)
#    com URL https; sem token, usa TARGET_REPO_URL como está (ssh com chave montada).
if [ ! -d /work/target/.git ]; then
  if [ -n "${GITHUB_CLONE_TOKEN:-}" ]; then
    git clone "https://x-access-token:${GITHUB_CLONE_TOKEN}@${TARGET_REPO_URL#https://}" /work/target
  else
    git clone "$TARGET_REPO_URL" /work/target
  fi
fi

# 4) daemon (servidor ASGI + laços; laço do motor conforme ROBOTO_ENGINE)
cd /opt/roboto
exec python3 -m roboto
