"""文档路由。上传需管理员 + 空间成员；触发后台归类任务。"""

import re
import unicodedata
import uuid
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.models.document import Document
from app.schemas.document import (
    DocumentMove,
    DocumentPublic,
    DocumentUploadAccepted,
    ProcessingTaskPublic,
    ReprocessAccepted,
)
from app.services.document_service import (
    create_reprocess_task,
    delete_document,
    list_document_tasks,
    list_documents,
    move_document,
    replace_document_content,
    upload_document,
)
from app.services.folder_service import get_folder_in_workspace
from app.services.usage_service import record_event
from app.services.workspace_service import is_member
from app.storage.base import get_storage
from app.tasks.worker import enqueue_classification

router = APIRouter(tags=["documents"])


def sanitize_filename(name: str) -> str:
    """规范化文件名：NFC Unicode → 移除控制字符 → 空格/不可见字符→下划线 → 合并连续下划线 → 保留扩展名。"""
    name = unicodedata.normalize("NFC", name)
    # 移除控制字符（\x00-\x1f \x7f）
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    # 替换空格、制表符等空白字符为下划线
    name = re.sub(r"[ \t]+", "_", name)
    # 路径分隔符也替换（防路径注入）
    name = re.sub(r"[/\\]", "_", name)
    # 合并连续下划线
    name = re.sub(r"_+", "_", name)
    # 去掉首尾下划线
    name = name.strip("_")
    # 保底：空文件名则 untitled
    return name or "untitled"


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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_id: uuid.UUID | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentUploadAccepted:
    # 上传为管理员操作，且须为该空间成员（越权校验 SECURITY #4）
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    await _ensure_member(session, workspace_id, current_user)

    if folder_id is not None:
        folder = await get_folder_in_workspace(
            session, folder_id=folder_id, workspace_id=workspace_id
        )
        if folder is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "目录不存在")

    data = await file.read()
    # 保留原始文件名（仅截取末段），规范化特殊字符，不添加路径前缀
    raw_name = PurePosixPath(file.filename or "untitled").name
    clean_name = sanitize_filename(raw_name)
    doc, task = await upload_document(
        session,
        workspace_id=workspace_id,
        filename=clean_name,
        mime_type=file.content_type or "application/octet-stream",
        data=data,
        uploaded_by=current_user.id,
        folder_id=folder_id,
    )
    # 触发后台归类 worker（进程内 asyncio，见 tasks/worker.py）
    enqueue_classification(task.id)

    async def _log_upload() -> None:
        async with SessionLocal() as s:
            await record_event(
                s,
                action="upload",
                user_id=current_user.id,
                workspace_id=workspace_id,
                meta={"filename": clean_name},
            )

    background_tasks.add_task(_log_upload)
    return DocumentUploadAccepted(id=doc.id, status=doc.status, task_id=task.id)


@router.get(
    "/workspaces/{workspace_id}/documents", response_model=list[DocumentPublic]
)
async def list_ws_documents(
    workspace_id: uuid.UUID,
    category: uuid.UUID | None = None,
    folder: uuid.UUID | None = None,
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
        folder_id=folder,
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


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    doc = await _get_doc_for_member(session, document_id, current_user)
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    await delete_document(session, doc=doc)


@router.patch("/documents/{document_id}/move", response_model=DocumentPublic)
async def move_doc(
    document_id: uuid.UUID,
    body: DocumentMove,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentPublic:
    doc = await _get_doc_for_member(session, document_id, current_user)
    # 目标目录须属于同一空间（None 表示移出目录）
    if body.folder_id is not None:
        folder = await get_folder_in_workspace(
            session, folder_id=body.folder_id, workspace_id=doc.workspace_id
        )
        if folder is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "目标目录不存在")
    doc = await move_document(session, doc=doc, folder_id=body.folder_id)
    return DocumentPublic.model_validate(doc)


@router.post(
    "/documents/{document_id}/replace",
    response_model=DocumentUploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def replace_doc(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentUploadAccepted:
    doc = await _get_doc_for_member(session, document_id, current_user)
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")
    data = await file.read()
    raw_name = PurePosixPath(file.filename or doc.title).name
    clean_name = sanitize_filename(raw_name)
    task = await replace_document_content(
        session,
        doc=doc,
        filename=clean_name,
        mime_type=file.content_type or "application/octet-stream",
        data=data,
    )
    enqueue_classification(task.id)
    return DocumentUploadAccepted(id=doc.id, status="processing", task_id=task.id)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """下载原文。JWT + 空间成员校验（Q7）；强制 attachment + nosniff（SECURITY #5）。"""
    doc = await _get_doc_for_member(session, document_id, current_user)
    data = await get_storage().read_bytes(doc.storage_key)

    async def _log_download() -> None:
        async with SessionLocal() as s:
            await record_event(
                s,
                action="download",
                user_id=current_user.id,
                workspace_id=doc.workspace_id,
                meta={"document_id": str(document_id)},
            )

    background_tasks.add_task(_log_download)
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.title)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


_PREVIEWABLE_INLINE = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    # text/html 和 image/svg+xml 可嵌入脚本，不允许 inline 渲染（改走 content_text 回退）
    "text/plain",
    "text/csv",
}


@router.get("/documents/{document_id}/preview")
async def preview_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """返回文件内容用于浏览器内联预览。PDF/图片直接 inline；其余回退到 content_text 纯文本。"""
    doc = await _get_doc_for_member(session, document_id, current_user)
    mime = doc.mime_type or "application/octet-stream"

    if mime in _PREVIEWABLE_INLINE:
        data = await get_storage().read_bytes(doc.storage_key)
        return Response(
            content=data,
            media_type=mime,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{quote(doc.title)}",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=300",
            },
        )

    # 非直接可预览类型：返回已提取的纯文本（归类阶段产出）
    text = doc.content_text or doc.summary or "（该文件类型暂不支持在线预览）"
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(doc.title + '.txt')}",
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
