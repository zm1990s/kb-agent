"""文档业务逻辑：上传（存原文 + 建处理任务）、查询。

隔离：所有查询强制带 workspace 过滤（SECURITY #4）。
存储：storage_key 由服务端生成，与客户端文件名解耦（SECURITY #5）。
"""

import uuid
from datetime import UTC, datetime, timedelta

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
    folder_id: uuid.UUID | None = None,
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
        folder_id=folder_id,
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


async def list_document_tasks(
    session: AsyncSession, *, document_id: uuid.UUID
) -> list[ProcessingTask]:
    stmt = (
        select(ProcessingTask)
        .where(ProcessingTask.document_id == document_id)
        .order_by(ProcessingTask.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    tag: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """列出空间内文档，可按分类/目录/标签/标题关键词过滤。强制 workspace 过滤（SECURITY #4）。"""
    stmt = select(Document).where(
        Document.workspace_id == workspace_id,
        Document.deleted_at.is_(None),
    )
    if category_id is not None:
        stmt = stmt.where(Document.category_id == category_id)
    if folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    if tag is not None:
        # ARRAY 包含：tags @> ARRAY[tag]
        stmt = stmt.where(Document.tags.contains([tag]))
    if search:
        stmt = stmt.where(Document.title.ilike(f"%{search}%"))
    stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def move_document(
    session: AsyncSession, *, doc: Document, folder_id: uuid.UUID | None
) -> Document:
    """把文档移动到目标目录（folder_id=None 表示移出目录/根）。"""
    doc.folder_id = folder_id
    await session.commit()
    await session.refresh(doc)
    return doc


async def rename_document(session: AsyncSession, *, doc: Document, title: str) -> Document:
    doc.title = title
    await session.commit()
    await session.refresh(doc)
    return doc


async def delete_document(session: AsyncSession, *, doc: Document) -> None:
    """软删除：打上 deleted_at 时间戳，进入回收站；存储文件保留至清理任务执行。"""
    doc.deleted_at = datetime.now(UTC)
    await session.commit()


async def restore_document(session: AsyncSession, *, doc: Document) -> None:
    """从回收站恢复：清除 deleted_at。"""
    doc.deleted_at = None
    await session.commit()


async def list_trashed_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """列出回收站中的文档（已软删除，按删除时间倒序）。"""
    stmt = (
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.deleted_at.is_not(None),
        )
        .order_by(Document.deleted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def purge_expired_trash(
    session: AsyncSession, *, retention_days: int = 30
) -> int:
    """物理删除超过保留期的回收站文档（DB 行 + 存储文件）。返回清理数量。"""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    stmt = select(Document).where(Document.deleted_at < cutoff)
    docs = list((await session.execute(stmt)).scalars().all())
    storage = get_storage()
    for doc in docs:
        key = doc.storage_key
        await session.delete(doc)
        await session.flush()
        try:
            await storage.delete(key)
        except FileNotFoundError:
            pass
    await session.commit()
    return len(docs)


async def replace_document_content(
    session: AsyncSession,
    *,
    doc: Document,
    filename: str,
    mime_type: str,
    data: bytes,
) -> ProcessingTask:
    """替换文档原文：覆盖存储、重置元数据、置回 processing 并新建归类任务。

    索引/摘要/标签/分类将由归类 worker 重新生成（重建索引）。
    """
    storage = get_storage()
    await storage.save(doc.storage_key, data)  # 覆盖同 key

    doc.title = filename
    doc.mime_type = mime_type
    doc.summary = None
    doc.tags = []
    doc.content_text = None
    doc.search_tsv = None
    doc.category_id = None
    doc.status = "processing"

    task = ProcessingTask(id=uuid.uuid4(), document_id=doc.id, kind="classify")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def create_reprocess_task(
    session: AsyncSession, *, document_id: uuid.UUID
) -> ProcessingTask:
    """为文档新建一个 queued 的归类任务，并把文档置回 processing。"""
    doc = await session.get(Document, document_id)
    if doc is not None:
        doc.status = "processing"
    task = ProcessingTask(id=uuid.uuid4(), document_id=document_id, kind="classify")
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task
