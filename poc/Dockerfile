# PoC do fleet (N3): tudo num container isolado — build/test do repo-alvo (Playwright),
# roboto (daemon), Claude Code + claude-code-router (-> OpenRouter/Qwen).
# NOTA: versões/pacotes marcados "validar" não foram exercitados sem rede; confira no 1º build.
FROM mcr.microsoft.com/playwright:v1.48.0-jammy

# Node já vem na imagem Playwright; habilita pnpm (versão do .nvmrc/engines do alvo).
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

# Python 3.11 (roboto) + git + gettext (envsubst)
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI + claude-code-router (validar nomes/versões dos pacotes npm)
RUN npm install -g @anthropic-ai/claude-code @musistudio/claude-code-router

WORKDIR /opt/roboto
COPY pyproject.toml ./
COPY src ./src
RUN pip3 install --break-system-packages -e .

COPY poc/ccr.config.json /opt/roboto/poc/ccr.config.json
COPY poc/entrypoint.sh /usr/local/bin/poc-entrypoint
RUN chmod +x /usr/local/bin/poc-entrypoint

ENTRYPOINT ["poc-entrypoint"]
