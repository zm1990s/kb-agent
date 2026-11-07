-- Per-answer scope and failure information survive history reloads.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS retrieval JSONB NOT NULL DEFAULT '{}'::jsonb;
