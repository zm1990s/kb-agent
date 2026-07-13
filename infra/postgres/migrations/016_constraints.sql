-- 016: 补充数据完整性约束

-- group_permissions.module：限定为已知模块名
ALTER TABLE group_permissions
    ADD CONSTRAINT chk_gp_module
    CHECK (module IN ('chat', 'documents', 'workspaces', 'users', 'settings', 'stats', 'whatsnew'))
    NOT VALID;
ALTER TABLE group_permissions VALIDATE CONSTRAINT chk_gp_module;

-- group_rules：限定 field / op 取值
ALTER TABLE group_rules
    ADD CONSTRAINT chk_gr_field
    CHECK (field IN ('email_domain', 'email', 'role'))
    NOT VALID;
ALTER TABLE group_rules VALIDATE CONSTRAINT chk_gr_field;

ALTER TABLE group_rules
    ADD CONSTRAINT chk_gr_op
    CHECK (op IN ('equals', 'endswith', 'contains'))
    NOT VALID;
ALTER TABLE group_rules VALIDATE CONSTRAINT chk_gr_op;

-- folders：加 parent_id 索引（树形查询性能）
CREATE INDEX IF NOT EXISTS ix_folders_parent ON folders (parent_id);

-- documents：加 uploaded_by 索引
CREATE INDEX IF NOT EXISTS ix_documents_uploaded_by ON documents (uploaded_by);
