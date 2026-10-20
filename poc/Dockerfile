# PoC do fleet (N3): tudo num container isolado — build/test do repo-alvo (Playwright),
# roboto (daemon), Claude Code + claude-code-router (-> OpenRouter/Qwen).
# NOTA: versões/pacotes marcados "validar" não foram exercitados sem rede; confira no 1º build.
# base noble (Ubuntu 24.04) => Python 3.12 (roboto exige >=3.11; jammy tem só 3.10)
FROM mcr.microsoft.com/playwright:v1.48.0-noble

# Node já vem na imagem Playwright; habilita pnpm (versão do .nvmrc/engines do alvo).
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# Python + venv + git + gettext (envsubst)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv git gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI + claude-code-router (validar nomes/versões dos pacotes npm)
RUN npm install -g @anthropic-ai/claude-code @musistudio/claude-code-router

# venv dedicado: evita PEP 668 (externally-managed) e garante pip novo (sem --break-system-packages)
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /opt/roboto
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e ".[engine]"  # inclui claude-agent-sdk (motor Claude Code)

COPY poc/ccr.config.json /opt/roboto/poc/ccr.config.json
COPY poc/smoke.py /opt/roboto/poc/smoke.py
COPY poc/check_config.py /opt/roboto/poc/check_config.py
COPY poc/run_engine.py /opt/roboto/poc/run_engine.py
COPY poc/migrate.py /opt/roboto/poc/migrate.py
COPY migrations /opt/roboto/migrations
COPY poc/entrypoint.sh /usr/local/bin/poc-entrypoint
RUN chmod +x /usr/local/bin/poc-entrypoint

ENTRYPOINT ["poc-entrypoint"]
