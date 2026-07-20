-- 扩展 schedule_type 约束以支持 weekly / monthly
ALTER TABLE scheduled_tasks
    DROP CONSTRAINT IF EXISTS scheduled_tasks_schedule_type_check;

ALTER TABLE scheduled_tasks
    ADD CONSTRAINT scheduled_tasks_schedule_type_check
        CHECK (schedule_type IN ('interval', 'daily', 'weekly', 'monthly'));
