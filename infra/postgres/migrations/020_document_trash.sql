-- 020: 文档回收站 —— 软删除字段
ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_documents_deleted_at ON documents (deleted_at)
    WHERE deleted_at IS NOT NULL;
