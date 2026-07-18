"""Skill Hub 路由（全平台共享）。

Skill 不再绑定 workspace（workspace_id=NULL 即全平台），任何登录用户可检索、使用；
创建/上传需要 skills:write 权限；改删需创建者或 admin。
审计端点要求 admin。
"""

import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.schemas.skill import (
    SkillAuditLogPublic,
    SkillCreate,
    SkillFilePreview,
    SkillFromConversationFile,
    SkillGroupPermissionPublic,
    SkillPermissionUpdate,
    SkillPublic,
    SkillSummary,
    SkillUpdate,
    SkillVisibilityUpdate,
)
from app.services import skill_service

router = APIRouter(prefix="/skills", tags=["skills"])


async def _require_write(session: AsyncSession, user: User) -> None:
    """校验 skills:write 权限（admin 绕过）。"""
    if user.role == "admin":
        return
    from app.services.rbac_service import effective_permissions

    perms = await effective_permissions(session, user=user)
    if perms.get("skills") != "write":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要 skills:write 权限")


# ── 审计（放在 /{skill_id} 之前避免路由冲突）─────────────────────────────────

@router.get("/audit", response_model=list[SkillAuditLogPublic])
async def list_audit(
    skill_id: uuid.UUID | None = None,
    limit: int = 100,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[SkillAuditLogPublic]:
    logs = await skill_service.list_audit_logs(
        session, workspace_id=None, skill_id=skill_id, limit=limit
    )
    return [SkillAuditLogPublic.model_validate(lg) for lg in logs]


# ── 列表 / 检索 ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SkillSummary])
async def list_skills(
    search: str | None = None,
    category: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[SkillSummary]:
    skills = await skill_service.list_hub_skills(
        session, user=current_user, search=search, category=category
    )
    emails = await skill_service.resolve_creator_emails(session, skills)
    out: list[SkillSummary] = []
    for s in skills:
        summary = SkillSummary.model_validate(s)
        summary.created_by_email = emails.get(s.created_by) if s.created_by else None
        out.append(summary)
    return out


@router.post("", response_model=SkillPublic, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillPublic:
    await _require_write(session, current_user)
    skill = await skill_service.create_skill(
        session,
        user=current_user,
        workspace_id=None,
        name=body.name,
        description=body.description,
        content=body.content,
        category=body.category,
        tags=body.tags,
        is_public=body.is_public,
    )
    return SkillPublic.model_validate(skill)


@router.post("/upload", response_model=SkillPublic, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillPublic:
    """上传 .md / .zip / .skill 文件创建 Skill。"""
    await _require_write(session, current_user)
    data = await file.read()
    parsed = skill_service.parse_skill_upload(file.filename or "skill.md", data)
    if not parsed.get("content"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件内容为空")
    skill = await skill_service.create_skill(
        session,
        user=current_user,
        workspace_id=None,
        name=parsed["name"],
        description=parsed.get("description"),
        content=parsed["content"],
        category=parsed.get("category"),
        tags=parsed.get("tags") or [],
        is_public=True,
        # 多文件包：原样保留整包，供调用时解包给 Agent
        bundle_data=data if parsed.get("has_bundle") else None,
    )
    return SkillPublic.model_validate(skill)


_SKILL_FILE_SUFFIXES = (".md", ".zip", ".skill")


async def _read_conversation_skill_file(
    session: AsyncSession,
    *,
    user: User,
    conversation_id: uuid.UUID,
    filename: str,
) -> bytes:
    """校验权限+归属+文件名，返回会话工作目录中该文件的字节内容。

    预览/创建共用。抛 HTTPException（403/404/400）。
    """
    from pathlib import PurePosixPath

    from app.services.chat_service import get_conversation_for_user
    from app.storage.base import get_storage
    from app.storage.local import StorageError

    await _require_write(session, user)

    # 会话归属校验（不泄漏存在性）
    conv = await get_conversation_for_user(
        session, conversation_id=conversation_id, user_id=user.id
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    # 防穿越：只保留纯文件名
    safe_name = PurePosixPath(filename).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法文件名")
    if not safe_name.lower().endswith(_SKILL_FILE_SUFFIXES):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "仅支持 .md / .zip / .skill 文件"
        )

    storage = get_storage()
    # 聊天+ 会话工作目录与工作区解耦，前缀为 chatplus/conv_{id}（与 chat.py 一致）
    key = f"chatplus/conv_{conversation_id}/{safe_name}"
    try:
        return await storage.read_bytes(key)
    except (FileNotFoundError, StorageError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在") from exc


@router.get("/conversation-file-preview", response_model=SkillFilePreview)
async def preview_skill_from_conversation_file(
    conversation_id: uuid.UUID,
    filename: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillFilePreview:
    """预览会话文件的 frontmatter，供「存为 Skill」弹窗预填；缺字段留空。"""
    from pathlib import PurePosixPath

    data = await _read_conversation_skill_file(
        session,
        user=current_user,
        conversation_id=conversation_id,
        filename=filename,
    )
    safe_name = PurePosixPath(filename).name
    # derive=False：只取 frontmatter 显式字段，缺失留空让用户填写
    parsed = skill_service.parse_skill_upload(safe_name, data, derive=False)
    return SkillFilePreview(
        name=parsed.get("name"),
        description=parsed.get("description"),
        category=parsed.get("category"),
        tags=parsed.get("tags") or [],
    )


@router.post(
    "/from-conversation-file",
    response_model=SkillPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_skill_from_conversation_file(
    body: SkillFromConversationFile,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillPublic:
    """把聊天+ 会话目录里 Agent 生成的文件（.md/.zip/.skill）存为 Skill。

    本人确认即可：需 skills:write 且是该会话属主。
    """
    from pathlib import PurePosixPath

    data = await _read_conversation_skill_file(
        session,
        user=current_user,
        conversation_id=body.conversation_id,
        filename=body.filename,
    )
    safe_name = PurePosixPath(body.filename).name
    parsed = skill_service.parse_skill_upload(safe_name, data)
    if not parsed.get("content"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "文件内容为空")

    # 覆盖合并：body 优先，留空用文件解析值
    skill = await skill_service.create_skill(
        session,
        user=current_user,
        workspace_id=None,
        name=body.name or parsed["name"],
        description=body.description or parsed.get("description"),
        content=parsed["content"],
        category=body.category or parsed.get("category"),
        tags=body.tags if body.tags is not None else (parsed.get("tags") or []),
        is_public=body.is_public,
        # 多文件包：原样保留整包，供调用时解包给 Agent
        bundle_data=data if parsed.get("has_bundle") else None,
    )
    return SkillPublic.model_validate(skill)


@router.get("/{skill_id}", response_model=SkillPublic)
async def get_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillPublic:
    skill = await skill_service.get_skill(session, skill_id=skill_id, user=current_user)
    pub = SkillPublic.model_validate(skill)
    emails = await skill_service.resolve_creator_emails(session, [skill])
    pub.created_by_email = emails.get(skill.created_by) if skill.created_by else None
    return pub


@router.get("/{skill_id}/download")
async def download_skill(
    skill_id: uuid.UUID,
    fmt: Literal["zip", "skill"] = Query(default="zip", alias="format"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """下载 Skill 为 .zip 或 .skill（均为 zip 容器，内含 SKILL.md）。"""
    data, filename, media_type = await skill_service.build_skill_download(
        session, skill_id=skill_id, user=current_user, fmt=fmt
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{skill_id}", response_model=SkillPublic)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillPublic:
    skill = await skill_service.update_skill(
        session,
        skill_id=skill_id,
        user=current_user,
        name=body.name,
        description=body.description,
        content=body.content,
        category=body.category,
        tags=body.tags,
    )
    return SkillPublic.model_validate(skill)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await skill_service.delete_skill(session, skill_id=skill_id, user=current_user)


@router.patch("/{skill_id}/visibility", response_model=SkillPublic)
async def set_visibility(
    skill_id: uuid.UUID,
    body: SkillVisibilityUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillPublic:
    skill = await skill_service.set_skill_visibility(
        session, skill_id=skill_id, user=current_user, is_public=body.is_public
    )
    return SkillPublic.model_validate(skill)


@router.post("/{skill_id}/permissions", response_model=SkillGroupPermissionPublic)
async def grant_permission(
    skill_id: uuid.UUID,
    body: SkillPermissionUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SkillGroupPermissionPublic:
    perm = await skill_service.grant_skill_permission(
        session,
        skill_id=skill_id,
        group_id=body.group_id,
        level=body.level,
        user=current_user,
    )
    return SkillGroupPermissionPublic.model_validate(perm)


@router.delete(
    "/{skill_id}/permissions/{group_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_permission(
    skill_id: uuid.UUID,
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await skill_service.revoke_skill_permission(
        session, skill_id=skill_id, group_id=group_id, user=current_user
    )
