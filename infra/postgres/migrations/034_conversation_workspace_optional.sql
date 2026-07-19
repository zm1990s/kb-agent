-- 聊天+ 会话与工作区解耦：会话不再必须绑定工作区（工作区降级为每轮可选上下文）。
-- 原始「聊天」(source='chat') 仍会传入 workspace_id，不受影响。
ALTER TABLE conversations ALTER COLUMN workspace_id DROP NOT NULL;
