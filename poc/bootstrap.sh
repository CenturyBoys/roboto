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

# 1) corepack já vem atualizado na imagem (Dockerfile, como root) + COREPACK_INTEGRITY_KEYS=0;
#    aqui só garante o enable (o provisionamento da versão PINADA acontece no install abaixo).
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
  finish "✅ PRONTO: $PM $ver + deps instaladas — ambiente operável" 0
else
  say "---- fim do log ----"; tail -8 "$LOG"
  finish "❌ FALHOU: '$PM install' não passou — ver $LOG" 1
fi
