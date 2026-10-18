-- 0001_init — núcleo durável (DESIGN-nucleo.md: D8/D9/D10/D11)
-- Postgres. `tenant` em toda tabela = isolamento por empresa (D17).
-- Schema é a fonte da verdade dos dados (migrations), não código (determinismo).

CREATE TABLE IF NOT EXISTS run (
    id              BIGINT      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant          TEXT        NOT NULL,
    repo            TEXT        NOT NULL,
    issue_id        TEXT        NOT NULL,
    agent           TEXT        NOT NULL,
    state           TEXT        NOT NULL,          -- queued|running|waiting|verifying|done|failed|abandoned
    attempt         INT         NOT NULL DEFAULT 0,
    lease_until     TIMESTAMPTZ,                   -- varredura reclama lease expirado (D8)
    idempotency_key TEXT        NOT NULL,          -- head_sha+evento+nº (B)
    agents_md_sha   TEXT,                          -- versão de regra por run (D11)
    prompt_version  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant, idempotency_key)
);
CREATE INDEX IF NOT EXISTS run_state_idx ON run (tenant, state);

-- run journal (trilha / resume — M)
CREATE TABLE IF NOT EXISTS run_event (
    id       BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    run_id   BIGINT      NOT NULL REFERENCES run (id),
    type     TEXT        NOT NULL,
    data     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS run_event_run_idx ON run_event (run_id, at);

-- outbox: efeitos exactly-once — gravar->commit->publicar (D9)
CREATE TABLE IF NOT EXISTS outbox (
    id         BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant     TEXT        NOT NULL,
    run_id     BIGINT      REFERENCES run (id),
    kind       TEXT        NOT NULL,               -- open_pr | telegram_notify | publish_event ...
    payload    JSONB       NOT NULL,
    dedup_key  TEXT        NOT NULL,
    status     TEXT        NOT NULL DEFAULT 'pending',  -- pending | sent
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at    TIMESTAMPTZ,
    UNIQUE (tenant, dedup_key)
);
CREATE INDEX IF NOT EXISTS outbox_pending_idx ON outbox (status, created_at);

-- auditoria de chamada de modelo — custo/observabilidade/reprodutibilidade (D10/D11)
CREATE TABLE IF NOT EXISTS llm_call (
    id             BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant         TEXT        NOT NULL,
    run_id         BIGINT      REFERENCES run (id),
    repo           TEXT,
    provider       TEXT        NOT NULL,           -- openrouter | typesafe ...
    model          TEXT        NOT NULL,
    tier           TEXT        NOT NULL,           -- judge | cheap | frontier
    tokens_in      INT         NOT NULL DEFAULT 0,
    tokens_out     INT         NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0,
    latency_ms     INT,
    prompt_version TEXT,
    agents_md_sha  TEXT,
    skill_version  TEXT,
    confidence     NUMERIC(5, 4),
    outcome        TEXT,
    at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS llm_call_tenant_at_idx ON llm_call (tenant, at);
