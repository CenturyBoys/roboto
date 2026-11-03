-- Rascunho de breakdown de épico (#203): persiste a proposta EDITÁVEL por (tenant, repo, issue) pra
-- sobreviver a F5 e troca de dispositivo (durável). 1 linha por épico (upsert). items_json = a lista
-- de esqueletos (title/points/depends_on_prev) serializada. A verdade canônica são as sub-issues no
-- GitHub depois do "Criar" (D15); isto é só o rascunho em edição — apagado ao materializar/descartar.
CREATE TABLE IF NOT EXISTS breakdown_draft (
    tenant     TEXT        NOT NULL,
    repo       TEXT        NOT NULL,
    issue_id   TEXT        NOT NULL,
    items_json TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant, repo, issue_id)
);
