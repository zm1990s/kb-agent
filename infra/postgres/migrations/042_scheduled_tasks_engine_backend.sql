-- 定时任务：新增 engine_backend 列，支持用户为每个定时任务选择执行引擎
ALTER TABLE scheduled_tasks
    ADD COLUMN IF NOT EXISTS engine_backend VARCHAR(30) NOT NULL DEFAULT 'claude_cli';
