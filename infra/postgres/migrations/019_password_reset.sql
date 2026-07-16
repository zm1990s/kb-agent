-- 自助找回密码：密码重置验证码相关字段
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS reset_code_hash TEXT        NULL,
  ADD COLUMN IF NOT EXISTS reset_code_exp  TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS reset_attempts  INT         NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reset_rate_exp  TIMESTAMPTZ NULL;
