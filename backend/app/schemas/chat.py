"""M3 · 对话检索的请求/响应 schema。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    workspace_id: uuid.UUID | None = None  # None = 检索所有有权限的空间
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    # Legacy IDs are validated for access but no longer filter retrieval scope.
    agent_ids: list[str] | None = Field(default=None, max_length=100)


class SourceRef(BaseModel):
    doc_id: str | None = None
    title: str
    download_url: str = ""
    id: str | None = None
    citation_id: str | None = None
    source_type: str = "workspace"
    agent_id: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    url: str | None = None
    excerpt: str | None = None
    locator: str | None = None
    content_kind: str | None = None
    product: str | None = None
    version: str | None = None
    published_at: str | None = None
    updated_at: str | None = None
    retrieved_at: str | None = None
    uploaded_at: str | None = None
    document_count: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    conversation_id: uuid.UUID
    error_key: str | None = None
    agent_runs: list[dict] = Field(default_factory=list)
    warning: str | None = None


class MessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    sources: list
    retrieval: dict = Field(default_factory=dict)
    attachments: list = []
    output_files: list = []
    created_at: datetime


class ConversationHistory(BaseModel):
    conversation_id: uuid.UUID
    messages: list[MessagePublic]


class ConversationCreate(BaseModel):
    workspace_id: uuid.UUID
    source: str = "chat"


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID | None
    title: str | None
    pinned: bool
    created_at: datetime


class ConversationUpdate(BaseModel):
    title: str | None = None
    pinned: bool | None = None


class SaveFileToLibrary(BaseModel):
    """把聊天+ 会话工作目录里的成果文件保存进文档库。"""

    workspace_id: uuid.UUID
    folder_id: uuid.UUID | None = None


class ConversationExportRequest(BaseModel):
    format: Literal["docx", "md", "pdf"]
    message_ids: list[uuid.UUID] | None = None  # None = 全部消息


class ConversationExportToLibraryRequest(ConversationExportRequest):
    workspace_id: uuid.UUID
    folder_id: uuid.UUID | None = None
