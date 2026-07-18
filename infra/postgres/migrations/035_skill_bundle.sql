-- 多文件 Skill：保留上传的 .zip/.skill 整包（含 SKILL.md 外的附属文件，如脚本）。
-- bundle_key 指向 storage 里保存的整包（skills/{id}/bundle.zip）；纯文本 Skill 为 NULL。
ALTER TABLE skills ADD COLUMN IF NOT EXISTS bundle_key TEXT;
