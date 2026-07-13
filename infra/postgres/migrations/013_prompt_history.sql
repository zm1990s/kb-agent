-- 提示词历史版本表（每次保存追加一条，append-only）
CREATE TABLE IF NOT EXISTS prompt_history (
    id          SERIAL PRIMARY KEY,
    prompt_key  VARCHAR(200) NOT NULL,
    version     INTEGER NOT NULL,
    value       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (prompt_key, version)
);
CREATE INDEX IF NOT EXISTS idx_prompt_history_key
    ON prompt_history (prompt_key, version DESC);
