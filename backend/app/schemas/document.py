"""M2 · 分类/文档/任务的请求/响应 schema。

本文件在 M2-U1 先落 Category；documents / tasks schema 于后续 Unit 补充。
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None


class CategoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
