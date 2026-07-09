-- migration 010: 文档简介字段（2-3句话的通用简介，独立于详细摘要）
ALTER TABLE documents ADD COLUMN IF NOT EXISTS brief TEXT;
