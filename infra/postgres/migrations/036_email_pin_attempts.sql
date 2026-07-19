-- migration 036: email PIN 验证防暴力破解（错误计数 + 锁定时间）
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS verification_attempts   INT         NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS verification_locked_until TIMESTAMPTZ;
