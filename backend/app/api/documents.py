"""文档路由。上传需管理员 + 空间成员；触发后台归类任务。"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.models.document import Document
from app.schemas.document import (
    DocumentPublic,
    DocumentUploadAccepted,
    ProcessingTaskPublic,
    ReprocessAccepted,
)
from app.services.document_service import (
    create_reprocess_task,
    list_document_tasks,
    list_documents,
    upload_document,
)
from app.services.workspace_service import is_member
from app.storage.base import get_storage
from app.tasks.worker import enqueue_classification

router = APIRouter(tags=["documents"])


async def _ensure_member(session: AsyncSession, ws_id: uuid.UUID, user: User) -> None:
    if not await is_member(session, workspace_id=ws_id, user_id=user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")


async def _get_doc_for_member(
    session: AsyncSession, document_id: uuid.UUID, user: User
) -> Document:
    """取文档并校验当前用户是其所属空间成员；否则 404（不泄漏存在性）。"""
    doc = await session.get(Document, document_id)
    if doc is None or not await is_member(
        session, workspace_id=doc.workspace_id, user_id=user.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    return doc


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentUploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentUploadAccepted:
    # 上传为管理员操作，且须为该空间成员（越权校验 SECURITY #4）
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    await _ensure_member(session, workspace_id, current_user)

    data = await file.read()
    doc, task = await upload_document(
        session,
        workspace_id=workspace_id,
        filename=file.filename or "untitled",
        mime_type=file.content_type or "application/octet-stream",
        data=data,
        uploaded_by=current_user.id,
    )
    # 触发后台归类 worker（进程内 asyncio，见 tasks/worker.py）
    enqueue_classification(task.id)
    return DocumentUploadAccepted(id=doc.id, status=doc.status, task_id=task.id)


@router.get(
    "/workspaces/{workspace_id}/documents", response_model=list[DocumentPublic]
)
async def list_ws_documents(
    workspace_id: uuid.UUID,
    category: uuid.UUID | None = None,
    tag: str | None = None,
    page: int = 1,
    size: int = 50,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentPublic]:
    await _ensure_member(session, workspace_id, current_user)
    docs = await list_documents(
        session,
        workspace_id=workspace_id,
        category_id=category,
        tag=tag,
        limit=size,
        offset=(max(page, 1) - 1) * size,
    )
    return [DocumentPublic.model_validate(d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentPublic)
async def get_document_detail(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentPublic:
    doc = await _get_doc_for_member(session, document_id, current_user)
    return DocumentPublic.model_validate(doc)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """下载原文。JWT + 空间成员校验（Q7）；强制 attachment + nosniff（SECURITY #5）。"""
    doc = await _get_doc_for_member(session, document_id, current_user)
    data = await get_storage().read_bytes(doc.storage_key)
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.title}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/documents/{document_id}/tasks", response_model=list[ProcessingTaskPublic])
async def list_tasks(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ProcessingTaskPublic]:
    await _get_doc_for_member(session, document_id, current_user)
    tasks = await list_document_tasks(session, document_id=document_id)
    return [ProcessingTaskPublic.model_validate(t) for t in tasks]


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=ReprocessAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReprocessAccepted:
    # 重试为管理员操作，且须为该文档所属空间成员
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    await _get_doc_for_member(session, document_id, current_user)
    task = await create_reprocess_task(session, document_id=document_id)
    enqueue_classification(task.id)
    return ReprocessAccepted(task_id=task.id, status="queued")
