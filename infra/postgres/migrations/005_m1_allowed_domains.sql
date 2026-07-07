-- M1-U9 · 注册域名白名单（从环境变量迁到 DB，由管理员维护）
-- 完整域名相等匹配；空表 = 全拒绝注册。

CREATE TABLE IF NOT EXISTS allowed_domains (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain     TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
