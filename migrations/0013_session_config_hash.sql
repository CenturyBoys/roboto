-- 0013 — config_hash na session (#266): guard de resume incompatível.
-- Com o switcher de modelo por etapa (I) e o escalonamento (#242), um `resume` pode cair sob
-- modelo/tools diferente do que criou a sessão nativa → contexto/cache incoerente. Guardamos o hash
-- da config na sessão e só retomamos quando bate (ver app/session_guard). Derivado do Tucano.
ALTER TABLE session ADD COLUMN IF NOT EXISTS config_hash TEXT;
