"""Skill 管理的请求/响应 schema。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    content: str = Field(min_length=1)
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_public: bool = True


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    content: str | None = Field(default=None, min_length=1)
    category: str | None = None
    tags: list[str] | None = None


class SkillFromConversationFile(BaseModel):
    """把聊天+ 会话目录里 Agent 生成的文件存为 Skill。

    覆盖字段留空时使用文件解析出的默认值（parse_skill_upload）。
    """

    conversation_id: uuid.UUID
    filename: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_public: bool = True


class SkillFilePreview(BaseModel):
    """会话文件的 frontmatter 预览（供「存为 Skill」弹窗预填）。

    仅取 SKILL.md frontmatter 中显式存在的字段，缺失则为 None/空，让用户填写。
    """

    name: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)


class SkillVisibilityUpdate(BaseModel):
    is_public: bool


class SkillPermissionUpdate(BaseModel):
    group_id: uuid.UUID
    level: str = Field(pattern="^(read|write|none)$")


class SkillPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID | None
    name: str
    description: str | None
    content: str
    category: str | None = None
    tags: list[str] = []
    is_public: bool
    bundle_key: str | None = Field(default=None, exclude=True)
    created_by: uuid.UUID | None
    created_by_email: str | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False

    @computed_field
    def has_bundle(self) -> bool:
        return bool(self.bundle_key)


class SkillSummary(BaseModel):
    """列表视图（不含 content 全文）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID | None
    name: str
    description: str | None
    category: str | None = None
    tags: list[str] = []
    is_public: bool
    bundle_key: str | None = Field(default=None, exclude=True)
    created_by: uuid.UUID | None
    created_by_email: str | None = None
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False

    @computed_field
    def has_bundle(self) -> bool:
        return bool(self.bundle_key)


class SkillGroupPermissionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    skill_id: uuid.UUID
    group_id: uuid.UUID
    level: str


class SkillAuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID | None
    skill_id: uuid.UUID | None
    user_id: uuid.UUID | None
    action: str
    detail: dict
    created_at: datetime
