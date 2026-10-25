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

# 2) sobe o ccr (porta 3456) e espera a PORTA responder; aponta o Claude Code para ele.
#    Retry de verdade: o `ccr start` às vezes race/falha no boot — reemite até a porta subir.
for _ in $(seq 1 20); do
  curl -s -o /dev/null http://127.0.0.1:3456 && break
  ccr start >/tmp/ccr.log 2>&1 &
  sleep 2
done
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

# 4a') pré-semeia o onboarding do Claude Code CLI p/ o co-piloto em tmux (COPILOT_MODE=tmux) abrir
#      DIRETO no REPL: onboarding feito, trust do projeto aceito, aviso de bypass pulado. Assim o
#      `tmux send-keys` já encontra o prompt (sem travar em telas de confirmação).
python3 - "$TARGET_WORKDIR" <<'PY'
import json, os, sys
home = os.path.expanduser("~"); workdir = sys.argv[1]
def load(p):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return {}
cj = os.path.join(home, ".claude.json")
d = load(cj); d["hasCompletedOnboarding"] = True
d.setdefault("projects", {}).setdefault(workdir, {})["hasTrustDialogAccepted"] = True
with open(cj, "w") as f: json.dump(d, f)
sp = os.path.join(home, ".claude", "settings.json")
os.makedirs(os.path.dirname(sp), exist_ok=True)
s = load(sp); s["skipDangerousModePermissionPrompt"] = True
with open(sp, "w") as f: json.dump(s, f)
print("onboarding semeado p/", workdir)
PY

# 4b) terminal web (ttyd): anexa na tmux POR-RUN passada via ?arg=<sessão> (modo -a/url-arg). Assim
#     o botão "Terminal" do cockpit mostra a sessão REAL do motor; sem sessão, cai no terminal padrão.
if command -v ttyd >/dev/null 2>&1; then
  cat > /tmp/ttyd-attach.sh <<'SH'
#!/usr/bin/env bash
s="${1:-potter}"
[ "$s" = "potter" ] && exec tmux new -A -s potter
tmux attach -t "$s" 2>/dev/null || tmux new -A -s potter
SH
  chmod +x /tmp/ttyd-attach.sh
  cd /work 2>/dev/null || true
  ttyd -p 7681 -W -a -t fontSize=14 -t 'theme={"background":"#0f1115"}' \
    /tmp/ttyd-attach.sh >/tmp/ttyd.log 2>&1 &
  cd /opt/roboto
fi

# 4c) daemon completo: aplica migrações e sobe servidor ASGI + laços (motor conforme ROBOTO_ENGINE)
python3 poc/migrate.py
exec python3 -m roboto
