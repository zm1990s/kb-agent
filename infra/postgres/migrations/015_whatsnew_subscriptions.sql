-- 015: What's New 邮件订阅表
CREATE TABLE whatsnew_subscriptions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    frequency    TEXT NOT NULL CHECK (frequency IN ('weekly', 'biweekly', 'monthly')),
    last_sent_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);
