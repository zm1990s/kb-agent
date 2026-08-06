"""KB 录入的请求 schema。"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    """KB 录入保存请求：把富文本导出为 docx/pdf 存进目标空间。"""

    title: str = Field(min_length=1, max_length=200)
    format: Literal["docx", "pdf"]
    content_json: dict  # Tiptap 文档 JSON（{type:"doc", content:[...]}）
    content_html: str | None = None
    workspace_id: uuid.UUID | None = None  # 未传时回退到管理员配置的默认空间
