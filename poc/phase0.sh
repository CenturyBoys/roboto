#!/usr/bin/env bash
# Fase 0 do PoC (N3): valida o ENCANAMENTO sem token/secret e sem tocar o GitHub.
# Prova: imagem builda · Postgres sobe · ferramentas presentes (node/pnpm/python/claude/ccr/
# playwright) · roboto importa · o laço claim->motor roda com StubEngine (run -> VERIFYING).
# Uso: ./poc/phase0.sh   (KEEP=1 mantém os containers no fim)
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f poc/compose.poc.yml)
[ -f poc/.env.poc ] && COMPOSE+=(--env-file poc/.env.poc)

pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFALHA\033[0m %s\n' "$1"; exit 1; }

echo "== 1/6 prereqs =="
docker version >/dev/null 2>&1 || fail "docker indisponível"
docker compose version >/dev/null 2>&1 || fail "docker compose indisponível"
pass "docker + compose"

echo "== 2/6 build da imagem do PoC (pode demorar no 1º build) =="
"${COMPOSE[@]}" build poc || fail "build da imagem"
pass "imagem construída"

echo "== 3/6 Postgres =="
"${COMPOSE[@]}" up -d db
status=""
for _ in $(seq 1 20); do
  cid="$("${COMPOSE[@]}" ps -q db)"
  status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || true)"
  [ "$status" = healthy ] && break
  sleep 2
done
[ "$status" = healthy ] || fail "db não ficou healthy"
pass "db healthy"

echo "== 4/6 ferramentas na imagem (informativo — claude/ccr/playwright importam p/ a Fase 1) =="
"${COMPOSE[@]}" run --rm --no-deps --entrypoint bash poc -lc '
  echo "  node    $(node --version 2>/dev/null || echo AUSENTE)"
  echo "  pnpm    $(pnpm --version 2>/dev/null || echo AUSENTE)"
  echo "  python  $(python3 --version 2>/dev/null || echo AUSENTE)"
  echo "  claude  $(claude --version 2>/dev/null || echo AUSENTE)"
  echo "  ccr     $(ccr -v 2>/dev/null || ccr version 2>/dev/null || echo AUSENTE)"
  echo "  pwright $(npx --yes playwright --version 2>/dev/null || echo AUSENTE)"
' || true

echo "== 5/6 roboto importa + smoke do loop (StubEngine) =="
"${COMPOSE[@]}" run --rm --entrypoint bash poc -lc \
  'python3 -c "import roboto" && python3 poc/smoke.py' \
  && pass "loop claim->motor OK (run -> VERIFYING)" || fail "smoke do loop"

echo "== 6/6 teardown =="
if [ "${KEEP:-0}" = 1 ]; then
  echo "  (KEEP=1: mantendo containers de pé)"
else
  "${COMPOSE[@]}" down -v && pass "ambiente limpo"
fi

echo ""
echo "Fase 0 concluída. Encanamento provado sem gastar token."
echo "Próximo: preencha poc/.env.poc e rode a Fase 1 com ROBOTO_ENGINE=claude_code."
