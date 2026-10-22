-- Config do fleet no banco (trilha O): fonte ÚNICA da config operacional. A origem pode ser o
-- .env (semeado no boot) ou a tela de setup do cockpit — tudo acaba aqui. DATABASE_URL e
-- CONSOLE_TOKEN NÃO ficam aqui (são bootstrap, só via env). Dev/bootstrap; prod pode usar vault (D4).
CREATE TABLE IF NOT EXISTS app_config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
