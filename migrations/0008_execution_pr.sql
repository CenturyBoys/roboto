-- PR + diff da execução (trilha O, Fatia 4): o cockpit mostra o diff sem precisar de cliente GitHub
-- (o motor já busca o diff no ciclo de review; aqui a gente persiste o último por execução). 1 linha
-- por run (upsert). Verdade canônica segue no GitHub (D15); isto é cache operacional p/ a UI.
CREATE TABLE IF NOT EXISTS execution_pr (
    execution_id BIGINT      PRIMARY KEY REFERENCES run (id),
    number       INTEGER     NOT NULL,
    url          TEXT        NOT NULL DEFAULT '',
    diff         TEXT        NOT NULL DEFAULT '',
    updated_at   TIMESTAMPTZ NOT NULL
);
