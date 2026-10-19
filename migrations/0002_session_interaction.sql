-- 0002 — session + interaction (D23). execution = tabela `run` (0001).
-- Três conceitos distintos (N): session (trabalho do motor), execution (=run),
-- interaction (pergunta/decisão pendente). IDs internos; o id NATIVO do motor fica em session.

-- sessão de trabalho de um motor de coding (Codex/Claude Code) para uma execução
CREATE TABLE IF NOT EXISTS session (
    id                BIGINT      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant            TEXT        NOT NULL,
    execution_id      BIGINT      NOT NULL REFERENCES run (id),
    engine            TEXT        NOT NULL,          -- codex | claude_code
    native_session_id TEXT,                          -- id da sessão NO motor (mapeado, não confundido)
    state             TEXT        NOT NULL DEFAULT 'active',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS session_exec_idx ON session (execution_id);

-- pergunta/decisão humana pendente (request_human_input — D24)
CREATE TABLE IF NOT EXISTS interaction (
    id                 BIGINT      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant             TEXT        NOT NULL,
    execution_id       BIGINT      NOT NULL REFERENCES run (id),
    session_id         BIGINT      REFERENCES session (id),
    kind               TEXT        NOT NULL,          -- question | decision | approval
    prompt             TEXT        NOT NULL,
    options            JSONB       NOT NULL DEFAULT '[]'::jsonb,
    status             TEXT        NOT NULL DEFAULT 'pending',  -- pending|answered|expired|cancelled
    channel_message_id TEXT,                           -- id da msg no canal (reply-routing, §4/§6)
    answer             TEXT,
    answered_by        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ,
    answered_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS interaction_pending_idx ON interaction (tenant, status);
-- resposta por reply localiza a interação pelo message_id (único por tenant)
CREATE UNIQUE INDEX IF NOT EXISTS interaction_msg_idx
    ON interaction (tenant, channel_message_id) WHERE channel_message_id IS NOT NULL;
