-- D30: cursor de canal persistido — o daemon retoma de onde leu (não reprocessa msg antiga no restart).
CREATE TABLE IF NOT EXISTS channel_cursor (
    tenant     TEXT        NOT NULL,
    channel    TEXT        NOT NULL,     -- ex.: 'telegram'
    cursor_val BIGINT      NOT NULL,     -- offset opaco do canal (próximo update_id)
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant, channel)
);
