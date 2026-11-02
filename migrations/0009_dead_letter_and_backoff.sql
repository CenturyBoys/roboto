-- 0009_dead_letter_and_backoff — Trilha B (#163)
-- Retry com backoff exponencial + dead-letter com contexto + replay.
-- Postgres. Schema é a fonte da verdade (determinismo primeiro).

-- backoff: run/efeito só re-elegível quando now >= next_attempt_at.
ALTER TABLE run    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS attempt         INT NOT NULL DEFAULT 0;
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
-- status do outbox agora inclui 'dead' (pending | sent | dead)

-- dead-letter: item que esgotou as tentativas, com contexto p/ diagnóstico e replay manual.
CREATE TABLE IF NOT EXISTS dead_letter (
    id         BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant     TEXT        NOT NULL,
    source     TEXT        NOT NULL,               -- effect | run
    ref_id     BIGINT      NOT NULL,               -- id do outbox/run original
    kind       TEXT        NOT NULL,               -- kind do efeito, ou agent do run
    payload    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error      TEXT        NOT NULL DEFAULT '',
    attempts   INT         NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dead_letter_tenant_idx ON dead_letter (tenant, id DESC);
