-- 修正 RBAC module 约束：真正生效的是 016 建立的 chk_gp_module，
-- 029/032 误操作了另一个不存在的约束名，导致 skills/feature_kb/chatplus 无法授权。
ALTER TABLE group_permissions DROP CONSTRAINT IF EXISTS chk_gp_module;
ALTER TABLE group_permissions DROP CONSTRAINT IF EXISTS group_permissions_module_check;

ALTER TABLE group_permissions
    ADD CONSTRAINT chk_gp_module
    CHECK (module IN (
        'chat', 'documents', 'workspaces', 'users',
        'settings', 'stats', 'whatsnew',
        'chatplus', 'skills', 'feature_kb'
    ));
