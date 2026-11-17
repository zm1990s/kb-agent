-- Global resource collection (URL bookmarks and HTML tool files).
-- No workspace_id — resources are shared across all workspaces.
CREATE TABLE IF NOT EXISTS resources (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(500) NOT NULL,
    description  TEXT,
    type         VARCHAR(10) NOT NULL CHECK (type IN ('url', 'html')),
    url          TEXT,
    storage_key  TEXT,
    created_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_resources_created_by ON resources (created_by);
