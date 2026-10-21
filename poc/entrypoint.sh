#!/usr/bin/env bash
# Entrypoint do PoC: sobe o claude-code-router (-> OpenRouter/Qwen), clona o repo-alvo e
# roda o daemon roboto. Fase 0: ROBOTO_ENGINE=stub (encanamento). Fase 1: claude_code.
set -euo pipefail

: "${OPENROUTER_API_KEY:?defina OPENROUTER_API_KEY no .env.poc}"
: "${TARGET_REPO_URL:?defina TARGET_REPO_URL (ex.: https://github.com/arenavalendo/main.git)}"
# modo PAT: 1 token serve p/ API e clone — reaproveita GITHUB_API_TOKEN se CLONE não vier
GITHUB_CLONE_TOKEN="${GITHUB_CLONE_TOKEN:-${GITHUB_API_TOKEN:-}}"

# 1) config do router a partir do template (injeta a chave do OpenRouter)
mkdir -p "$HOME/.claude-code-router"
envsubst < /opt/roboto/poc/ccr.config.json > "$HOME/.claude-code-router/config.json"

# 2) sobe o ccr (porta 3456) e espera ficar pronto; aponta o Claude Code para ele
ccr start >/tmp/ccr.log 2>&1 &
for _ in $(seq 1 15); do ccr status >/dev/null 2>&1 && break; sleep 1; done
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-http://127.0.0.1:3456}"
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-sk-ccr-noop}"      # ccr ignora; chave real = OPENROUTER
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-$ANTHROPIC_API_KEY}"  # redundância (bearer)

# 3) checkout do repo-alvo em /work/<owner>/<repo> (o motor roda com cwd AQUI — casa com drive_turn).
#    repo privado: GITHUB_CLONE_TOKEN (PAT) via https; sem token, usa TARGET_REPO_URL (ssh).
TARGET_DIR="/work/${ROBOTO_DEFAULT_REPO:-target}"
if [ ! -d "$TARGET_DIR/.git" ]; then
  mkdir -p "$(dirname "$TARGET_DIR")"
  if [ -n "${GITHUB_CLONE_TOKEN:-}" ]; then
    git clone "https://x-access-token:${GITHUB_CLONE_TOKEN}@${TARGET_REPO_URL#https://}" "$TARGET_DIR"
  else
    git clone "$TARGET_REPO_URL" "$TARGET_DIR"
  fi
fi
export TARGET_WORKDIR="$TARGET_DIR"

cd /opt/roboto

# 4a) smoke observável da Fase 1 (POC_TASK setado): roda só o motor e imprime eventos; sem DB/daemon
if [ -n "${POC_TASK:-}" ]; then
  exec python3 poc/run_engine.py "$POC_TASK"
fi

# 4b) terminal web (ttyd) servindo um tmux no /work — pra assistir/operar o container no browser (D25)
if command -v ttyd >/dev/null 2>&1; then
  cd /work 2>/dev/null || true
  ttyd -p 7681 -W -t fontSize=14 -t 'theme={"background":"#0f1115"}' \
    tmux new -A -s potter >/tmp/ttyd.log 2>&1 &
  cd /opt/roboto
fi

# 4c) daemon completo: aplica migrações e sobe servidor ASGI + laços (motor conforme ROBOTO_ENGINE)
python3 poc/migrate.py
exec python3 -m roboto
