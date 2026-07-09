-- migration 009: 用量事件追踪表
CREATE TABLE IF NOT EXISTS usage_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,          -- login / upload / chat / download / reprocess
    meta        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_usage_events_user_id     ON usage_events (user_id);
CREATE INDEX IF NOT EXISTS ix_usage_events_created_at  ON usage_events (created_at);
CREATE INDEX IF NOT EXISTS ix_usage_events_action      ON usage_events (action);
