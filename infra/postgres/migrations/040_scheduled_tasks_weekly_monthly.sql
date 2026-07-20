-- 040: 定时任务新增每周/每月调度支持
-- week_day: 0=周一 … 6=周日（ISO weekday - 1），仅 weekly 模式使用
-- month_day: 1–31，仅 monthly 模式使用

ALTER TABLE scheduled_tasks
    ADD COLUMN IF NOT EXISTS week_day   SMALLINT CHECK (week_day BETWEEN 0 AND 6),
    ADD COLUMN IF NOT EXISTS month_day  SMALLINT CHECK (month_day BETWEEN 1 AND 31);
