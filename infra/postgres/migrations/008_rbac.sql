-- F4-F7 · 用户管理 + 用户组 + RBAC + 空间按组授权

-- F4: 用户启用/禁用
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

-- F5: 用户组
CREATE TABLE IF NOT EXISTS groups (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 组的自动入组规则（多维：字段 + 操作符 + 值）
CREATE TABLE IF NOT EXISTS group_rules (
    id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    group_id UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    field    TEXT NOT NULL,        -- email_domain / email / role
    op       TEXT NOT NULL,        -- equals / endswith / contains
    value    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_group_rules_group ON group_rules (group_id);

-- 用户↔组
CREATE TABLE IF NOT EXISTS group_members (
    group_id UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    user_id  UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_group_members_user ON group_members (user_id);

-- F6: RBAC —— 组 × 模块 × 读写
CREATE TABLE IF NOT EXISTS group_permissions (
    group_id UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    module   TEXT NOT NULL,        -- chat / documents / workspaces / users / settings
    level    TEXT NOT NULL CHECK (level IN ('none', 'read', 'write')),
    PRIMARY KEY (group_id, module)
);

-- F7: 空间按组授权（与个人成员并存）
CREATE TABLE IF NOT EXISTS workspace_group_grants (
    workspace_id UUID NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    group_id     UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    role_in_ws   TEXT NOT NULL CHECK (role_in_ws IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (workspace_id, group_id)
);
CREATE INDEX IF NOT EXISTS ix_ws_group_grants_group ON workspace_group_grants (group_id);
