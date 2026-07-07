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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.schemas.document import DocumentUploadAccepted
from app.services.document_service import upload_document
from app.services.workspace_service import is_member

router = APIRouter(tags=["documents"])


async def _ensure_member(session: AsyncSession, ws_id: uuid.UUID, user: User) -> None:
    if not await is_member(session, workspace_id=ws_id, user_id=user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")


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
    # M2-U5 将在此处触发后台归类 worker（进程内 asyncio）。
    return DocumentUploadAccepted(id=doc.id, status=doc.status, task_id=task.id)
