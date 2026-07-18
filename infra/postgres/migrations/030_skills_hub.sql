-- Skill Hub：补充可检索卡片所需的分类与标签字段（additive）。
ALTER TABLE skills
    ADD COLUMN IF NOT EXISTS category TEXT,
    ADD COLUMN IF NOT EXISTS tags     TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS ix_skills_category ON skills(category);
