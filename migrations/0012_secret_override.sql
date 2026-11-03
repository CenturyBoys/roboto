-- Override humano do secret-scan (H): o operador marca um run barrado por segredo como
-- FALSO-POSITIVO e libera o push (ex.: token de exemplo legítimo num teste de redação). Uma linha
-- por run (idempotente). O ciclo lê isto antes de abortar; o override é AUDITADO no feed da execução.
CREATE TABLE IF NOT EXISTS secret_override (
    run_id BIGINT      PRIMARY KEY REFERENCES run (id),
    at     TIMESTAMPTZ NOT NULL
);
