#!/usr/bin/env bash
# Valida poc/.env.poc (reexecutável): roda o check dentro da imagem do PoC contra o env injetado.
# Uso: ./poc/check-config.sh   (precisa da imagem já construída — rode ./poc/phase0.sh ao menos 1x)
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f poc/.env.poc ] || { echo "poc/.env.poc não existe — copie de poc/.env.poc.example e preencha"; exit 1; }

docker compose -f poc/compose.poc.yml --env-file poc/.env.poc \
  run --rm --no-deps --entrypoint bash poc -lc 'python3 poc/check_config.py'
