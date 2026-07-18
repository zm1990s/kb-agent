-- 扩展 RBAC module 枚举：新增 skills 和 feature_kb

ALTER TABLE group_permissions
    DROP CONSTRAINT IF EXISTS group_permissions_module_check;

ALTER TABLE group_permissions
    ADD CONSTRAINT group_permissions_module_check
    CHECK (module IN (
        'chat', 'documents', 'workspaces', 'users',
        'settings', 'stats', 'whatsnew',
        'skills', 'feature_kb'
    ));
