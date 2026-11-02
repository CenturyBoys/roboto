-- 0010_pr_review_state — Trilha B (#166): gatilho por POLLING de atividade de PR com debounce.
-- Sem webhook (decisão do dono): o daemon pergunta "o que mudou?" e só avalia quando o PR estabiliza.
-- Guarda, por (tenant, repo, pr), o último sha visto, quando mudou pela última vez, e o sha já avaliado.

CREATE TABLE IF NOT EXISTS pr_review_state (
    tenant           TEXT        NOT NULL,
    repo             TEXT        NOT NULL,
    pr_number        INT         NOT NULL,
    last_seen_sha    TEXT        NOT NULL DEFAULT '',
    last_activity_at TIMESTAMPTZ NOT NULL,
    reviewed_sha     TEXT        NOT NULL DEFAULT '',   -- '' = nunca avaliado
    PRIMARY KEY (tenant, repo, pr_number)
);
