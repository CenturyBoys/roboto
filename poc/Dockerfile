# PoC do fleet (N3): tudo num container isolado — build/test do repo-alvo (Playwright),
# roboto (daemon), Claude Code + claude-code-router (-> OpenRouter/Qwen).
# NOTA: versões/pacotes marcados "validar" não foram exercitados sem rede; confira no 1º build.
# Estágio UI: builda o cockpit React (mesmo do Dockerfile principal) — o PoC serve o SPA (trilha O).
FROM node:24-slim AS ui
WORKDIR /app/web/ui
COPY web/ui/package.json web/ui/package-lock.json ./
RUN npm ci
COPY web/ui ./
RUN npm run build  # -> /app/src/roboto/web/static

# base noble (Ubuntu 24.04) => Python 3.12 (roboto exige >=3.11; jammy tem só 3.10)
FROM mcr.microsoft.com/playwright:v1.48.0-noble

# NODE POR-REPO (sem hardcode de versão): a imagem traz o Node base (p/ a tooling do fleet), mas o
# bootstrap instala em runtime o Node que CADA repo pede (.nvmrc/engines) em ~/.node-current — que
# vem ANTES no PATH. Assim a imagem não tem opinião sobre versão; o repo manda.
ENV PATH="/home/pwuser/.node-current/bin:$PATH"
# corepack@latest: o bundled (0.29.x) tem chaves velhas e falha com 'Cannot find matching keyid' ao
# provisionar pnpm novo. COREPACK_INTEGRITY_KEYS=0: pula a verificação (sandbox) — a versão PINADA
# pelo `packageManager` do repo-alvo é provisionada em runtime.
RUN npm install -g corepack@latest && corepack enable
ENV COREPACK_INTEGRITY_KEYS=0

# Python + venv + git + gettext (envsubst) + base Rust de busca (ripgrep/fd) p/ token economy (F)
# + tmux (sessão observável) + ttyd (terminal web no browser, D25)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv git gettext-base curl ripgrep fd-find tmux xz-utils \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
      -o /usr/local/bin/ttyd && chmod +x /usr/local/bin/ttyd

# Claude Code CLI + claude-code-router (validar nomes/versões dos pacotes npm)
RUN npm install -g @anthropic-ai/claude-code @musistudio/claude-code-router

# venv dedicado: evita PEP 668 (externally-managed) e garante pip novo (sem --break-system-packages)
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/roboto
COPY pyproject.toml ./
COPY src ./src
# SPA do cockpit (trilha O) buildado no estágio `ui`:
COPY --from=ui /app/src/roboto/web/static ./src/roboto/web/static
RUN pip install -e ".[engine]"  # inclui claude-agent-sdk (motor Claude Code)

COPY poc/ccr.config.json /opt/roboto/poc/ccr.config.json
COPY poc/smoke.py /opt/roboto/poc/smoke.py
COPY poc/check_config.py /opt/roboto/poc/check_config.py
COPY poc/run_engine.py /opt/roboto/poc/run_engine.py
COPY poc/run_cycle.py /opt/roboto/poc/run_cycle.py
COPY poc/migrate.py /opt/roboto/poc/migrate.py
COPY poc/bootstrap.sh /opt/roboto/poc/bootstrap.sh
COPY migrations /opt/roboto/migrations
COPY poc/entrypoint.sh /usr/local/bin/poc-entrypoint
RUN chmod +x /usr/local/bin/poc-entrypoint

# roda como NÃO-root: Claude Code exige isso p/ bypassPermissions (autonomia total: git/pnpm/PR).
RUN id -u pwuser >/dev/null 2>&1 || useradd -m -u 1000 pwuser
RUN mkdir -p /work /home/pwuser && chown -R pwuser:pwuser /work /home/pwuser /opt/roboto
ENV HOME=/home/pwuser
USER pwuser

# ide_cc (code-intel MCP): navegação/edição semântica verificada = menos token (F). Em ~/.local/bin.
RUN curl -fsSL https://raw.githubusercontent.com/CenturyBoys/ide_cc/main/install.sh \
      | INSTALL_LSP=1 bash || echo "aviso: ide_cc não instalado (segue sem code-intel)"
ENV PATH="/home/pwuser/.local/bin:$PATH"

ENTRYPOINT ["poc-entrypoint"]
