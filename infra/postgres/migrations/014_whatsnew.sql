-- 014: What's New 摘要报告表
CREATE TABLE IF NOT EXISTS whatsnew_reports (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    period_start TIMESTAMPTZ NOT NULL,
    period_end   TIMESTAMPTZ NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    doc_ids      UUID[] NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_whatsnew_reports_ws ON whatsnew_reports (workspace_id, created_at DESC);
