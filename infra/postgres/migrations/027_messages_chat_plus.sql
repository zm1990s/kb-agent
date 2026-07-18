-- 聊天+ 文件能力：messages 表新增附件和输出文件列

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS attachments  JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS output_files JSONB NOT NULL DEFAULT '[]';
