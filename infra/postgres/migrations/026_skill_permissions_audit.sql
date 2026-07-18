-- Skill 组级权限 + 审计日志

CREATE TABLE IF NOT EXISTS skill_group_permissions (
    id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    skill_id UUID NOT NULL REFERENCES skills (id) ON DELETE CASCADE,
    group_id UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    level    TEXT NOT NULL CHECK (level IN ('read', 'write', 'none')),
    UNIQUE (skill_id, group_id)
);

CREATE INDEX IF NOT EXISTS ix_skill_group_perm_skill ON skill_group_permissions (skill_id);
CREATE INDEX IF NOT EXISTS ix_skill_group_perm_group ON skill_group_permissions (group_id);

CREATE TABLE IF NOT EXISTS skill_audit_logs (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID REFERENCES workspaces (id) ON DELETE SET NULL,
    skill_id     UUID REFERENCES skills (id) ON DELETE SET NULL,
    user_id      UUID REFERENCES users (id) ON DELETE SET NULL,
    action       TEXT NOT NULL CHECK (action IN (
                     'created', 'updated', 'deleted',
                     'visibility_changed', 'permission_granted', 'permission_revoked',
                     'used_in_chat')),
    detail       JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_skill_audit_ws    ON skill_audit_logs (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_skill_audit_skill ON skill_audit_logs (skill_id, created_at DESC);
