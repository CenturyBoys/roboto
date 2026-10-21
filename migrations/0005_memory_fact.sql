-- Trilha G (second brain): fatos/decisões do projeto. Verdade = texto; busca = índice FTS derivado.
CREATE TABLE IF NOT EXISTS memory_fact (
    id         BIGSERIAL PRIMARY KEY,
    tenant     TEXT        NOT NULL,
    kind       TEXT        NOT NULL,          -- decisão | fato | handoff | arquitetura
    ref        TEXT        NOT NULL DEFAULT '',  -- issue/PR/épico relacionado
    text       TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    -- índice FTS derivado (rebuildável): recall determinístico por BM25-like, sem LLM (trilha G/F)
    fts        tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', text)) STORED
);
CREATE INDEX IF NOT EXISTS memory_fact_fts ON memory_fact USING GIN (fts);
CREATE INDEX IF NOT EXISTS memory_fact_tenant ON memory_fact (tenant);
