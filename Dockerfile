# Imagem do roboto (D1: containerizado). Multi-stage: o estágio Node (build do SPA) fica FORA da
# imagem final — ela leva só o Python slim + deps (de wheels, sem toolchain) + código + SPA.

# Estágio 1: builda o cockpit React (trilha O). O vite escreve em /app/src/roboto/web/static.
FROM node:24-slim AS ui
WORKDIR /app/web/ui
COPY web/ui/package.json web/ui/package-lock.json ./
RUN npm ci
COPY web/ui ./
RUN npm run build

# Estágio 2: runtime Python mínimo (slim; deps vêm de wheels manylinux, sem compilar nada).
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Cria o usuário ANTES e copia já com dono certo (sem `chown -R`, que duplicaria camadas).
RUN useradd --create-home roboto
COPY --chown=roboto:roboto pyproject.toml ./
COPY --chown=roboto:roboto src ./src
COPY --chown=roboto:roboto migrations ./migrations
# SPA buildado no estágio `ui` (não versionado; gerado no build).
COPY --from=ui --chown=roboto:roboto /app/src/roboto/web/static ./src/roboto/web/static
RUN pip install -e .

USER roboto
# Sobe o daemon: servidor ASGI (cockpit web + webhook) + laços.
CMD ["python", "-m", "roboto"]
