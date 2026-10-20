-- D30: run carrega o chat de origem (Telegram) p/ ecoar status/pergunta de volta ao canal certo.
ALTER TABLE run ADD COLUMN IF NOT EXISTS origin_chat_id TEXT;
