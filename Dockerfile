# Imagem do roboto (decisão D1: containerizado). Runner/orquestrador rodam a partir desta base.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir -e .

# não-root (K: container não-root)
RUN useradd --create-home roboto && chown -R roboto:roboto /app
USER roboto

CMD ["python", "-c", "import roboto; print('roboto', roboto.__version__)"]
