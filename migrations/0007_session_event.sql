-- Feed legível do motor por execução (trilha O, Fatia 2): mensagens e tool-calls que o cockpit
-- transmite ao vivo (SSE). Append-only; ordenado por id. Verdade operacional "quente" (não é o
-- registro canônico — esse é a issue/PR no GitHub, D15/D30).
CREATE TABLE IF NOT EXISTS session_event (
    id           BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    tenant       TEXT        NOT NULL,
    execution_id BIGINT      NOT NULL REFERENCES run (id),
    session_id   BIGINT,
    kind         TEXT        NOT NULL,   -- message | tool_call
    text         TEXT        NOT NULL DEFAULT '',
    tool         TEXT        NOT NULL DEFAULT '',
    at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS session_event_exec_idx ON session_event (execution_id, id);
