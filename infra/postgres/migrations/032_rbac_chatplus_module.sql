-- 扩展 RBAC module 枚举：新增 chatplus（聊天+ 独立权限）
-- 注意：此处误操作了 group_permissions_module_check（并非生效约束），由 033 修正。
ALTER TABLE group_permissions
    DROP CONSTRAINT IF EXISTS group_permissions_module_check;

ALTER TABLE group_permissions
    ADD CONSTRAINT group_permissions_module_check
    CHECK (module IN (
        'chat', 'documents', 'workspaces', 'users',
        'settings', 'stats', 'whatsnew',
        'skills', 'feature_kb', 'chatplus'
    ));
