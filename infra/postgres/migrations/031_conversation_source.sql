-- 区分「聊天」与「聊天+」的会话来源，使两处历史互不干扰（additive）。
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'chat';

CREATE INDEX IF NOT EXISTS ix_conversations_source ON conversations(workspace_id, user_id, source);
