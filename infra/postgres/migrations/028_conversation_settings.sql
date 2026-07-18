-- 聊天+ 对话级配置（懒创建，无记录 = 使用默认）

CREATE TABLE IF NOT EXISTS conversation_settings (
    conversation_id  UUID PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
    active_skill_ids UUID[] NOT NULL DEFAULT '{}',
    doc_filter_ids   UUID[] NOT NULL DEFAULT '{}',
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
