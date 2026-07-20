-- 新增 cases 模块到 RBAC group_permissions 约束
ALTER TABLE group_permissions DROP CONSTRAINT IF EXISTS chk_gp_module;

ALTER TABLE group_permissions
    ADD CONSTRAINT chk_gp_module
    CHECK (module IN (
        'chat', 'documents', 'workspaces', 'users',
        'settings', 'stats', 'whatsnew',
        'chatplus', 'skills', 'feature_kb', 'cases'
    ));
