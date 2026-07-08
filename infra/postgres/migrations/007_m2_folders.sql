-- M2-U10 · 用户手动目录（文件夹树）。与 Agent 分类/标签无关。
-- documents.folder_id 单归属；删除文件夹时其下文档 folder_id 置空（不级联删文档）。

CREATE TABLE IF NOT EXISTS folders (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    parent_id    UUID REFERENCES folders (id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_folders_workspace ON folders (workspace_id);

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES folders (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_documents_folder ON documents (folder_id);
