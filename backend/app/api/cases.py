"""Case 录入路由：富文本导出为 docx/pdf，保存进管理员配置的默认空间。

产物即普通 documents 记录，走与上传一致的后台 AI 归类（status: processing→ready）。
权限复用 documents 模块 + 默认空间写权限（owner/editor）。
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.schemas.case import CaseCreate
from app.schemas.document import DocumentPublic
from app.services import case_service
from app.services.document_service import upload_document
from app.services.settings_service import get_case_default_workspace_id
from app.services.usage_service import record_event
from app.services.workspace_service import get_ws_role
from app.tasks.worker import enqueue_classification

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cases"])


async def _require_documents(session: AsyncSession, user: User) -> None:
    """要求用户对 documents 模块有权限（≥read）；admin 绕过。"""
    if user.role == "admin":
        return
    from app.services.rbac_service import effective_permissions

    perms = await effective_permissions(session, user=user)
    if perms.get("documents", "none") == "none":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无文档模块权限")


@router.post("/cases", response_model=DocumentPublic, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentPublic:
    """把 Case 富文本导出为 docx/pdf，存进默认空间（status=ready）。"""
    await _require_documents(session, current_user)

    # 默认空间：管理员在系统设置配置；未配置则 Case 录入不可用
    ws_id_str = await get_case_default_workspace_id(session)
    if not ws_id_str:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "管理员尚未配置 Case 默认保存空间")
    try:
        workspace_id = uuid.UUID(ws_id_str)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "默认空间配置无效") from exc

    # 目标空间写权限（全局 admin 或 owner/editor）
    role = await get_ws_role(session, workspace_id=workspace_id, user_id=current_user.id)
    if role not in ("owner", "editor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "对默认空间没有写入权限，请联系管理员")

    # 导出（Tiptap JSON → docx/pdf；纯文本由后续 AI 归类自行抽取，这里不再使用）
    try:
        data, mime_type, _plain_text = case_service.export_case(
            title=body.title,
            fmt=body.format,
            content_json=body.content_json,
            content_html=body.content_html,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    ext = "docx" if body.format == "docx" else "pdf"
    filename = f"{body.title}.{ext}"

    # 与普通上传一致：建 processing 文档 + 归类任务，入队后台 AI 整理
    doc, task = await upload_document(
        session,
        workspace_id=workspace_id,
        filename=filename,
        mime_type=mime_type,
        data=data,
        uploaded_by=current_user.id,
    )
    enqueue_classification(task.id)
    logger.info(
        "audit case_create user=%s ws=%s doc=%s task=%s fmt=%s",
        current_user.id, workspace_id, doc.id, task.id, body.format,
    )
    await record_event(
        session, action="case_create", user_id=current_user.id, workspace_id=workspace_id,
        meta={"document_id": str(doc.id), "format": body.format, "title": body.title},
    )
    return DocumentPublic.model_validate(doc)
