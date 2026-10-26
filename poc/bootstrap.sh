#!/usr/bin/env bash
# Bootstrap + VALIDAÇÃO do ambiente do repo-alvo (trilha K/H: determinismo).
#
# Regra clara: na 1ª subida, PREPARA a toolchain (corepack/pnpm/yarn/npm conforme o `packageManager`
# do repo), INSTALA as deps e VALIDA que dá pra operar. Se passar aqui, a implementação não trava por
# ambiente depois. É idempotente — rodar de novo só reconfirma. Uso: `bootstrap.sh <dir-do-repo>`.
#
# NÃO derruba o daemon: o entrypoint roda isto em background e grava o status em /tmp/env-status.
set -uo pipefail

DIR="${1:?uso: bootstrap.sh <dir-do-repo>}"
STATUS="/tmp/env-status"
LOG="/tmp/bootstrap.log"
: >"$LOG"

say() { echo "$*" | tee -a "$LOG"; }
finish() { echo "$1" >"$STATUS"; say "$1"; exit "${2:-0}"; }

cd "$DIR" 2>/dev/null || finish "❌ FALHOU: dir não existe: $DIR" 1
say "🔧 bootstrap do ambiente em $DIR"

if [ ! -f package.json ]; then
  finish "✅ PRONTO: sem package.json (não é projeto JS — nada a instalar)" 0
fi

# 0) NODE POR-REPO (genérico, não hardcoded): lê a versão que o REPO exige (.nvmrc tem prioridade;
#    senão o piso de engines.node) e instala o binário oficial em ~/.node-current (já no PATH). Assim
#    cada repo roda com o Node que pede (arenavalendo pina 24 no .nvmrc) — a imagem não tem opinião.
ensure_node() {
  local major cur arch file ver url dest
  major=$(sed -nE 's/^v?([0-9]+).*/\1/p' .nvmrc 2>/dev/null | head -1)
  [ -z "$major" ] && major=$(node -e "try{const e=(require('./package.json').engines||{}).node||'';const m=e.match(/([0-9]+)/);process.stdout.write(m?m[1]:'')}catch(e){}" 2>/dev/null)
  [ -z "$major" ] && { say "ℹ️  repo não fixa versão de Node — mantém $(node -v 2>/dev/null)"; return 0; }
  cur=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
  if [ "$cur" = "$major" ]; then say "✅ Node já na versão certa (v$cur, repo pede $major)"; return 0; fi
  case "$(uname -m)" in x86_64) arch=x64;; aarch64|arm64) arch=arm64;; *) arch=x64;; esac
  say "⬇️  Node: repo pede v$major, container tem v$cur — instalando v$major ($arch)…"
  file=$(curl -fsSL "https://nodejs.org/dist/latest-v${major}.x/SHASUMS256.txt" 2>/dev/null \
    | grep -oE "node-v[0-9.]+-linux-${arch}.tar.xz" | head -1)
  [ -z "$file" ] && { say "⚠️  não resolvi Node v$major — segue com v$cur"; return 0; }
  ver=${file#node-}; ver=${ver%%-*}
  url="https://nodejs.org/dist/${ver}/${file}"
  dest="$HOME/.node-${ver}"
  if [ ! -x "$dest/bin/node" ]; then
    curl -fsSL "$url" -o /tmp/node.tar.xz 2>>"$LOG" && mkdir -p "$dest" \
      && tar -xJf /tmp/node.tar.xz -C "$dest" --strip-components=1 2>>"$LOG" || {
        say "⚠️  download/extração do Node falhou — segue com v$cur"; return 0; }
  fi
  ln -sfn "$dest" "$HOME/.node-current"  # PATH já aponta p/ ~/.node-current/bin (Dockerfile)
  say "✅ Node $ver ativo ($(PATH="$HOME/.node-current/bin:$PATH" node -v 2>/dev/null))"
}
ensure_node

# 1) corepack do Node ativo + COREPACK_INTEGRITY_KEYS=0 (provisiona o pm PINADO no install abaixo).
corepack enable >>"$LOG" 2>&1 || true

# 2) detecta o gerenciador pelo campo packageManager (ou pelo lockfile)
PM=$(node -e "try{process.stdout.write(((require('./package.json').packageManager)||'').split('@')[0])}catch(e){}" 2>/dev/null)
[ -z "$PM" ] && [ -f pnpm-lock.yaml ] && PM=pnpm
[ -z "$PM" ] && [ -f yarn.lock ] && PM=yarn
[ -z "$PM" ] && PM=npm
say "📦 gerenciador: $PM ($(grep -o '"packageManager":[^,]*' package.json 2>/dev/null | head -1))"

# 3) instala deps (corepack provisiona a versão PINADA do packageManager) e VALIDA
say "⬇️  instalando deps ($PM install)... (pode demorar na 1ª vez)"
if "$PM" install >>"$LOG" 2>&1; then
  ver=$("$PM" -v 2>/dev/null)
  # descarta o CHURN do install (lockfile/package.json reescritos pelo pm) — o node_modules fica
  # (é untracked), mas a árvore volta ao estado commitado. Senão o `commit_all` da implementação
  # varreria o lockfile (+2000 linhas) pro PR, poluindo o diff.
  git checkout -- . >>"$LOG" 2>&1 || true
  finish "✅ PRONTO: node $(node -v 2>/dev/null) · $PM $ver + deps — ambiente operável" 0
else
  say "---- fim do log ----"; tail -8 "$LOG"
  finish "❌ FALHOU: '$PM install' não passou — ver $LOG" 1
fi
