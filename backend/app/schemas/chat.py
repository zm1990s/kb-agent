"""M3 · 对话检索的请求/响应 schema。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    workspace_id: uuid.UUID | None = None  # None = 自动定位到最相关空间
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


class SourceRef(BaseModel):
    doc_id: str
    title: str
    download_url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    conversation_id: uuid.UUID


class MessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    sources: list
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
