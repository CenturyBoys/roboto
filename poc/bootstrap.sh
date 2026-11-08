#!/usr/bin/env bash
# Bootstrap + VALIDAÇÃO do ambiente do repo-alvo (trilha K/H: determinismo primeiro).
#
# MULTI-ECOSSISTEMA + MONOREPO-AWARE: varre manifestos na RAIZ e em SUBPASTAS (bounded/pruned) e
# instala as deps com o toolchain certo de CADA ecossistema — não assume "é só JS". Cobre:
#   • JS/TS  (package.json) → corepack provisiona pnpm/yarn/npm PINADO; Node por-repo (.nvmrc/engines).
#            Monorepo com workspaces → 1 install na raiz cobre tudo; sem workspaces → install por pacote.
#   • Python (requirements.txt / pyproject.toml / setup.py) → uv se houver; senão poetry (projeto
#            poetry); senão venv por-dir + pip. Instala numa `.venv` local (não polui o venv do roboto).
#   • Go     (go.mod)      → go mod download.
#   • Rust   (Cargo.toml)  → cargo fetch.
# Manifesto encontrado mas toolchain AUSENTE no container → entra como FALHA explícita (não mascara:
# senão o `test` desse ecossistema quebraria por ambiente e o filtro de INFRA esconderia o buraco).
#
# É idempotente — rodar de novo só reconfirma. NÃO derruba o daemon: o entrypoint roda em background e
# grava o status em /tmp/env-status ("✅ PRONTO ..." / "❌ FALHOU ..."; o repo_profile lê "PRONTO").
# Uso: `bootstrap.sh <dir-do-repo>`.
set -uo pipefail

DIR="${1:?uso: bootstrap.sh <dir-do-repo>}"
STATUS="/tmp/env-status"
LOG="/tmp/bootstrap.log"
: >"$LOG"

say() { echo "$*" | tee -a "$LOG"; }
finish() { echo "$1" >"$STATUS"; say "$1"; exit "${2:-0}"; }
join() { local IFS="; "; echo "$*"; }

cd "$DIR" 2>/dev/null || finish "❌ FALHOU: dir não existe: $DIR" 1
say "🔧 bootstrap multi-ecossistema em $DIR"

PREP=()  # ecossistemas preparados, ex.: "js:pnpm(.)"
FAIL=()  # falhas, ex.: "go:toolchain ausente(./svc)"

# dirs (relativos) que contêm <arquivo-manifesto>, até 5 níveis, podando pastas de artefato/deps.
manifest_dirs() {
  find . -maxdepth 5 -type f -name "$1" \
    -not -path '*/node_modules/*' -not -path '*/.git/*'  -not -path '*/vendor/*' \
    -not -path '*/dist/*'         -not -path '*/build/*'  -not -path '*/target/*' \
    -not -path '*/.venv/*'        -not -path '*/.next/*'  -not -path '*/out/*' \
    2>/dev/null | sed -E 's#/[^/]+$##' | sort -u
}
has_tool() { command -v "$1" >/dev/null 2>&1; }
relname() { case "$1" in .|./) echo "raiz";; *) echo "${1#./}";; esac; }  # rótulo legível do dir

# ---------------------------------------------------------------- JS/TS (Node) --------------------
# NODE POR-REPO (genérico): lê a versão que o repo exige (.nvmrc tem prioridade; senão engines.node) e
# instala o binário oficial em ~/.node-current (já no PATH). A imagem não tem opinião de versão.
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
  url="https://nodejs.org/dist/${ver}/${file}"; dest="$HOME/.node-${ver}"
  if [ ! -x "$dest/bin/node" ]; then
    curl -fsSL "$url" -o /tmp/node.tar.xz 2>>"$LOG" && mkdir -p "$dest" \
      && tar -xJf /tmp/node.tar.xz -C "$dest" --strip-components=1 2>>"$LOG" || {
        say "⚠️  download/extração do Node falhou — segue com v$cur"; return 0; }
  fi
  ln -sfn "$dest" "$HOME/.node-current"  # PATH já aponta p/ ~/.node-current/bin (Dockerfile)
  say "✅ Node $ver ativo ($(PATH="$HOME/.node-current/bin:$PATH" node -v 2>/dev/null))"
}

prep_js() {  # arg: dir do package.json
  local d="$1" rel pm; rel=$(relname "$d")
  ( cd "$d" || exit 1
    pm=$(node -e "try{process.stdout.write(((require('./package.json').packageManager)||'').split('@')[0])}catch(e){}" 2>/dev/null)
    [ -z "$pm" ] && [ -f pnpm-lock.yaml ] && pm=pnpm
    [ -z "$pm" ] && [ -f yarn.lock ] && pm=yarn
    [ -z "$pm" ] && pm=npm
    say "📦 JS($rel): $pm install…"
    "$pm" install >>"$LOG" 2>&1
  ) && PREP+=("js:$(_pm_of "$d")($rel)") || FAIL+=("js:install falhou($rel)")
}
_pm_of() { ( cd "$1" 2>/dev/null && { node -e "try{process.stdout.write(((require('./package.json').packageManager)||'').split('@')[0]||'npm')}catch(e){process.stdout.write('npm')}" 2>/dev/null || echo npm; } ); }

# ---------------------------------------------------------------- Python --------------------------
prep_python() {  # arg: dir
  local d="$1" rel; rel=$(relname "$d")
  if has_tool uv; then
    ( cd "$d" || exit 1
      say "🐍 Python($rel): uv…"
      if [ -f pyproject.toml ]; then uv sync >>"$LOG" 2>&1
      else uv venv >>"$LOG" 2>&1 && uv pip install -r requirements.txt >>"$LOG" 2>&1; fi
    ) && { PREP+=("python:uv($rel)"); return; } || { FAIL+=("python:uv falhou($rel)"); return; }
  fi
  if has_tool poetry && grep -q '\[tool.poetry\]' "$d/pyproject.toml" 2>/dev/null; then
    ( cd "$d" && poetry install >>"$LOG" 2>&1 ) \
      && { PREP+=("python:poetry($rel)"); return; } || { FAIL+=("python:poetry falhou($rel)"); return; }
  fi
  if has_tool python3; then
    ( cd "$d" || exit 1
      say "🐍 Python($rel): venv + pip…"
      python3 -m venv .venv >>"$LOG" 2>&1 || exit 1
      if [ -f requirements.txt ]; then .venv/bin/pip install -r requirements.txt >>"$LOG" 2>&1
      else .venv/bin/pip install -e . >>"$LOG" 2>&1; fi
    ) && PREP+=("python:pip($rel)") || FAIL+=("python:pip falhou($rel)")
    return
  fi
  FAIL+=("python:toolchain ausente($rel)")
}

# ---------------------------------------------------------------- Go / Rust -----------------------
prep_go() {  # arg: dir
  local d="$1" rel; rel=$(relname "$d")
  has_tool go || { FAIL+=("go:toolchain ausente($rel)"); return; }
  say "🐹 Go($rel): go mod download…"
  ( cd "$d" && go mod download >>"$LOG" 2>&1 ) && PREP+=("go($rel)") || FAIL+=("go:download falhou($rel)")
}
prep_rust() {  # arg: dir
  local d="$1" rel; rel=$(relname "$d")
  has_tool cargo || { FAIL+=("rust:toolchain ausente($rel)"); return; }
  say "🦀 Rust($rel): cargo fetch…"
  ( cd "$d" && cargo fetch >>"$LOG" 2>&1 ) && PREP+=("rust($rel)") || FAIL+=("rust:fetch falhou($rel)")
}

# ================================================================ orquestração ====================
# JS: workspace (pnpm-workspace.yaml / campo "workspaces" na raiz) → 1 install na raiz cobre o monorepo
# inteiro; senão, instala POR pacote (cobre monorepo de package.json soltos, sem workspace manager).
JS_DIRS=$(manifest_dirs package.json)
if [ -n "$JS_DIRS" ]; then
  corepack enable >>"$LOG" 2>&1 || true
  if [ -f package.json ]; then ensure_node; fi
  if [ -f package.json ] && { [ -f pnpm-workspace.yaml ] || grep -q '"workspaces"' package.json 2>/dev/null; }; then
    say "🧩 monorepo JS com workspaces → install único na raiz"
    prep_js "."
  else
    say "🧩 JS sem workspace manager → install por pacote ($(echo "$JS_DIRS" | wc -l) dir[s])"
    while IFS= read -r d; do [ -n "$d" ] && prep_js "$d"; done <<<"$JS_DIRS"
  fi
fi

# Python: une os dirs dos 3 manifestos (dedup); instala uma vez por dir.
PY_DIRS=$( { manifest_dirs requirements.txt; manifest_dirs pyproject.toml; manifest_dirs setup.py; } | sort -u )
while IFS= read -r d; do [ -n "$d" ] && prep_python "$d"; done <<<"$PY_DIRS"

# Go / Rust
while IFS= read -r d; do [ -n "$d" ] && prep_go   "$d"; done <<<"$(manifest_dirs go.mod)"
while IFS= read -r d; do [ -n "$d" ] && prep_rust "$d"; done <<<"$(manifest_dirs Cargo.toml)"

# descarta o CHURN do install (lockfiles/manifestos reescritos pelos pms) — os dirs de deps
# (node_modules/.venv/target) são untracked e ficam; a árvore RASTREADA volta ao estado commitado,
# pra o `commit_all` da implementação não varrer lockfile (+milhares de linhas) pro PR.
git checkout -- . >>"$LOG" 2>&1 || true

# ================================================================ veredito ========================
if [ ${#PREP[@]} -eq 0 ] && [ ${#FAIL[@]} -eq 0 ]; then
  finish "✅ PRONTO: nenhum manifesto reconhecido (JS/Python/Go/Rust) — nada a instalar" 0
fi
if [ ${#FAIL[@]} -eq 0 ]; then
  finish "✅ PRONTO: $(join "${PREP[@]}") · node $(node -v 2>/dev/null) — ambiente operável" 0
else
  say "---- fim do log ----"; tail -8 "$LOG"
  ok="nenhum"; [ ${#PREP[@]} -gt 0 ] && ok="$(join "${PREP[@]}")"
  finish "❌ FALHOU: $(join "${FAIL[@]}") [preparados: $ok] — ver $LOG" 1
fi
