-- 定时任务表：支持 interval（每 N 分钟）和 daily（每天 HH:MM UTC）两种调度模式
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name             VARCHAR(200) NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    schedule_type    VARCHAR(20) NOT NULL CHECK (schedule_type IN ('interval', 'daily')),
    interval_minutes INT,       -- schedule_type='interval' 时有效，最小 5
    daily_hour       SMALLINT,  -- schedule_type='daily' 时有效，0-23（UTC）
    daily_minute     SMALLINT,  -- schedule_type='daily' 时有效，0-59（UTC）
    system_prompt    TEXT,
    initial_message  TEXT NOT NULL,
    skill_ids        UUID[] NOT NULL DEFAULT '{}',
    workspace_id     UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    locale           VARCHAR(10) NOT NULL DEFAULT 'zh',
    last_run_at      TIMESTAMPTZ,
    next_run_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_user
    ON scheduled_tasks (user_id);

CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_next_run
    ON scheduled_tasks (next_run_at)
    WHERE enabled = TRUE;
