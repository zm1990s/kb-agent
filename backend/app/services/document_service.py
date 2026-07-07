"""文档业务逻辑：上传（存原文 + 建处理任务）、查询。

隔离：所有查询强制带 workspace 过滤（SECURITY #4）。
存储：storage_key 由服务端生成，与客户端文件名解耦（SECURITY #5）。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, ProcessingTask
from app.storage.base import generate_storage_key, get_storage


class DocumentNotFoundError(Exception):
    """文档不存在（或不属于该 workspace）。"""


async def upload_document(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    filename: str,
    mime_type: str,
    data: bytes,
    uploaded_by: uuid.UUID,
) -> tuple[Document, ProcessingTask]:
    """存原文到 storage，建 processing 文档记录 + 归类任务（queued）。"""
    storage = get_storage()
    key = generate_storage_key(workspace_id)
    await storage.save(key, data)

    doc = Document(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        title=filename,
        storage_key=key,
        mime_type=mime_type,
        status="processing",
        uploaded_by=uploaded_by,
    )
    session.add(doc)
    task = ProcessingTask(id=uuid.uuid4(), document_id=doc.id, kind="classify")
    session.add(task)
    await session.commit()
    await session.refresh(doc)
    await session.refresh(task)
    return doc, task


async def get_document_in_workspace(
    session: AsyncSession, *, document_id: uuid.UUID, workspace_id: uuid.UUID
) -> Document | None:
    """按 id + workspace 取文档；跨空间返回 None（不泄漏存在性）。"""
    stmt = select(Document).where(
        Document.id == document_id, Document.workspace_id == workspace_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
