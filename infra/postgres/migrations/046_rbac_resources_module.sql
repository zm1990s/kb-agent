-- 扩展 RBAC module 枚举：新增 resources（资源收藏库）
ALTER TABLE group_permissions DROP CONSTRAINT IF EXISTS chk_gp_module;

ALTER TABLE group_permissions
    ADD CONSTRAINT chk_gp_module
    CHECK (module IN (
        'chat', 'documents', 'workspaces', 'users',
        'settings', 'stats', 'whatsnew',
        'chatplus', 'skills', 'feature_kb', 'cases', 'resources'
    ));
