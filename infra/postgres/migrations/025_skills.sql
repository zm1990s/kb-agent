-- Skill 管理：Skill 主表

CREATE TABLE IF NOT EXISTS skills (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID REFERENCES workspaces (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    description  TEXT,
    content      TEXT NOT NULL,
    is_public    BOOLEAN NOT NULL DEFAULT true,
    created_by   UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_skills_ws         ON skills (workspace_id);
CREATE INDEX IF NOT EXISTS ix_skills_created_by ON skills (created_by);
