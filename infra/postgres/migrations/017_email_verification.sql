-- 017: 邮箱验证字段
-- DEFAULT TRUE 保证存量用户不受影响（视为已验证）
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS email_verified         BOOL        NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS verification_token     TEXT        NULL,
  ADD COLUMN IF NOT EXISTS verification_token_exp TIMESTAMPTZ NULL;
