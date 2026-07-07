-- M2-U2 · 文档与处理任务
-- 严格按 DESIGN.md；只做 additive。

CREATE TABLE IF NOT EXISTS documents (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces (id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    storage_key  TEXT NOT NULL,
    mime_type    TEXT NOT NULL,
    category_id  UUID REFERENCES categories (id) ON DELETE SET NULL,
    summary      TEXT,
    tags         TEXT[] NOT NULL DEFAULT '{}',
    content_text TEXT,
    search_tsv   TSVECTOR,
    status       TEXT NOT NULL DEFAULT 'processing'
                 CHECK (status IN ('processing', 'ready', 'failed')),
    uploaded_by  UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_documents_search_tsv ON documents USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS ix_documents_ws_category ON documents (workspace_id, category_id);
CREATE INDEX IF NOT EXISTS ix_documents_ws_status ON documents (workspace_id, status);

-- processing_tasks（后台归类任务，可查进度/可重试）
CREATE TABLE IF NOT EXISTS processing_tasks (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id  UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    kind         TEXT NOT NULL DEFAULT 'classify',
    status       TEXT NOT NULL DEFAULT 'queued'
                 CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempts     INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    error        TEXT,
    logs         JSONB NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_processing_tasks_document ON processing_tasks (document_id);
CREATE INDEX IF NOT EXISTS ix_processing_tasks_status ON processing_tasks (status);
