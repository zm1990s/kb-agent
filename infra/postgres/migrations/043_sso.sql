-- SSO 联合登录：管理员登记的允许回调客户端 + 一次性授权码

CREATE TABLE sso_clients (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    uri_prefix  TEXT        NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 一次性授权码（code 明文不入库，存 SHA-256 hash）
CREATE TABLE sso_codes (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    code_hash    TEXT        NOT NULL UNIQUE,
    user_id      UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri TEXT        NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    used_at      TIMESTAMPTZ
);

CREATE INDEX ix_sso_codes_hash       ON sso_codes(code_hash);
CREATE INDEX ix_sso_codes_expires_at ON sso_codes(expires_at);
