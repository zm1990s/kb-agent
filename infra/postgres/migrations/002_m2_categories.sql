-- M2-U1 · 分类体系（管理员预定义，支持层级）
-- 严格按 DESIGN.md；只做 additive。

CREATE TABLE IF NOT EXISTS categories (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    parent_id    UUID REFERENCES categories (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_categories_workspace ON categories (workspace_id);
