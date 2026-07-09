-- migration 012: 合并 internal/partner → user；保留 admin
-- 1. 迁移存量数据
UPDATE users SET role = 'user' WHERE role IN ('internal', 'partner');

-- 2. 迁移组规则中的 role 字段值（如有 value='internal' 或 'partner'）
UPDATE group_rules SET value = 'user' WHERE field = 'role' AND value IN ('internal', 'partner');

-- 3. 重建 CHECK 约束
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'user'));
