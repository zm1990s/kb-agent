"""管理后台路由（F4-F6）：用户管理、用户组、RBAC。均需 admin。"""

import asyncio
import collections
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_admin
from app.core.logging_setup import get_log_dir
from app.models.auth import User
from app.schemas.rbac import (
    GroupCreate,
    GroupPermissionPublic,
    GroupPublic,
    GroupRuleCreate,
    GroupRulePublic,
    PermissionSet,
    ResetPasswordRequest,
    SetActiveRequest,
    SetRoleRequest,
    UserAdminView,
)
from app.services import rbac_service
from app.services.rbac_service import delete_user
from app.services.usage_service import get_chat_events, get_download_events, get_stats, record_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ── F4 用户管理 ────────────────────────────────────────

@router.get("/users", response_model=list[UserAdminView])
async def list_users(session: AsyncSession = Depends(get_session)):
    return await rbac_service.list_users(session)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """管理员删除用户（不可删除自身）。"""
    if user_id == current_admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能删除自己")
    if not await delete_user(session, user_id=user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    logger.info("audit admin delete_user admin=%s target=%s", current_admin.id, user_id)
    await record_event(session, action="admin_delete_user", user_id=current_admin.id,
                       meta={"target_user_id": str(user_id)})


@router.patch("/users/{user_id}/active", response_model=UserAdminView)
async def set_active(
    user_id: uuid.UUID,
    body: SetActiveRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await rbac_service.set_user_active(
        session, user_id=user_id, active=body.is_active
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    logger.info("audit admin set_active admin=%s target=%s active=%s",
                current_admin.id, user_id, body.is_active)
    await record_event(session, action="admin_set_user_active", user_id=current_admin.id,
                       meta={"target_user_id": str(user_id), "is_active": body.is_active})
    return user


@router.patch("/users/{user_id}/role", response_model=UserAdminView)
async def set_role(
    user_id: uuid.UUID,
    body: SetRoleRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await rbac_service.set_user_role(session, user_id=user_id, role=body.role)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    logger.info("audit admin set_role admin=%s target=%s role=%s",
                current_admin.id, user_id, body.role)
    await record_event(session, action="admin_set_user_role", user_id=current_admin.id,
                       meta={"target_user_id": str(user_id), "role": body.role})
    return user


@router.patch("/users/{user_id}/verify-email", response_model=UserAdminView)
async def set_email_verified(
    user_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """管理员手动将用户标记为邮箱已验证。"""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    user.email_verified = True
    user.verification_token = None
    user.verification_token_exp = None
    await session.commit()
    await session.refresh(user)
    logger.info("audit admin set_email_verified admin=%s target=%s", current_admin.id, user_id)
    return user


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await rbac_service.admin_reset_password(
        session, user_id=user_id, new_password=body.new_password
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    logger.info("audit admin reset_password admin=%s target=%s", current_admin.id, user_id)
    await record_event(session, action="admin_reset_password", user_id=current_admin.id,
                       meta={"target_user_id": str(user_id)})


# ── F5 用户组 ──────────────────────────────────────────

@router.get("/groups", response_model=list[GroupPublic])
async def list_groups(session: AsyncSession = Depends(get_session)):
    return await rbac_service.list_groups(session)


@router.post("/groups", response_model=GroupPublic, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    group = await rbac_service.create_group(session, name=body.name, description=body.description)
    logger.info("audit admin create_group admin=%s group=%s", current_admin.id, group.id)
    await record_event(session, action="admin_create_group", user_id=current_admin.id,
                       meta={"group_id": str(group.id), "name": body.name})
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if not await rbac_service.delete_group(session, group_id=group_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "组不存在")
    logger.info("audit admin delete_group admin=%s group=%s", current_admin.id, group_id)
    await record_event(session, action="admin_delete_group", user_id=current_admin.id,
                       meta={"group_id": str(group_id)})


@router.get("/groups/{group_id}/rules", response_model=list[GroupRulePublic])
async def list_rules(
    group_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await rbac_service.list_group_rules(session, group_id=group_id)


@router.post(
    "/groups/{group_id}/rules",
    response_model=GroupRulePublic,
    status_code=status.HTTP_201_CREATED,
)
async def add_rule(
    group_id: uuid.UUID,
    body: GroupRuleCreate,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rule = await rbac_service.add_group_rule(
        session, group_id=group_id, field=body.field, op=body.op, value=body.value
    )
    logger.info("audit admin add_rule admin=%s group=%s field=%s op=%s value=%s",
                current_admin.id, group_id, body.field, body.op, body.value)
    await record_event(session, action="admin_add_group_rule", user_id=current_admin.id,
                       meta={"group_id": str(group_id), "field": body.field,
                             "op": body.op, "value": body.value})
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if not await rbac_service.delete_group_rule(session, rule_id=rule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    logger.info("audit admin delete_rule admin=%s rule=%s", current_admin.id, rule_id)
    await record_event(session, action="admin_delete_group_rule", user_id=current_admin.id,
                       meta={"rule_id": str(rule_id)})


@router.get("/groups/{group_id}/members", response_model=list[UserAdminView])
async def group_members(
    group_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await rbac_service.list_group_members(session, group_id=group_id)


@router.post("/recompute-memberships")
async def recompute_memberships(
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    count = await rbac_service.recompute_all_memberships(session)
    logger.info("audit admin recompute_memberships admin=%s count=%d", current_admin.id, count)
    await record_event(session, action="admin_recompute_memberships", user_id=current_admin.id,
                       meta={"recomputed_users": count})
    return {"recomputed_users": count}


# ── F6 RBAC ────────────────────────────────────────────

@router.get("/groups/{group_id}/permissions", response_model=list[GroupPermissionPublic])
async def get_permissions(
    group_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await rbac_service.get_group_permissions(session, group_id=group_id)


@router.put("/groups/{group_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def set_permission(
    group_id: uuid.UUID,
    body: PermissionSet,
    current_admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    await rbac_service.set_group_permission(
        session, group_id=group_id, module=body.module, level=body.level
    )
    logger.info("audit admin set_permission admin=%s group=%s module=%s level=%s",
                current_admin.id, group_id, body.module, body.level)
    await record_event(session, action="admin_set_permission", user_id=current_admin.id,
                       meta={"group_id": str(group_id), "module": body.module, "level": body.level})


# 供前端获取「我的有效权限」以做菜单显隐/只读控制
@router.get("/my-permissions")
async def my_permissions(
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    # 注：此端点在 admin 下永远全 write；非 admin 的权限查询见 /auth/my-permissions
    return await rbac_service.effective_permissions(session, user=current_user)


# ── F9-5 用量报表 ─────────────────────────────────────

@router.get("/stats")
async def usage_stats(
    days: int = Query(30, ge=1, le=365),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """近 N 天用量统计：按天+动作聚合、活跃用户、总计。"""
    return await get_stats(session, days=days)


@router.get("/usage/downloads")
async def get_download_list(
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await get_download_events(session, days=days, offset=(page - 1) * page_size, limit=page_size)


@router.get("/usage/chats")
async def get_chat_list(
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await get_chat_events(session, days=days, offset=(page - 1) * page_size, limit=page_size)


# ── 日志查看 ──────────────────────────────────────────


@router.get("/logs")
async def list_log_files(_admin: User = Depends(require_admin)) -> list[dict]:
    """列出可用的日志文件（最新优先）。"""
    log_dir = get_log_dir()
    if not os.path.isdir(log_dir):
        return []
    import re as _re
    _log_pat = _re.compile(r'^[\w.-]+\.log(\.\d+)?$')
    files = sorted(
        (f for f in os.listdir(log_dir) if _log_pat.match(f)),
        key=lambda f: os.path.getmtime(os.path.join(log_dir, f)),
        reverse=True,
    )
    return [
        {
            "name": f,
            "size": os.path.getsize(os.path.join(log_dir, f)),
            "mtime": os.path.getmtime(os.path.join(log_dir, f)),
        }
        for f in files
    ]


def _tail_file(path: str, lines: int) -> str:
    """高效读取文件末尾 N 行（不把整个大文件加载到内存）。"""
    deque: collections.deque[str] = collections.deque(maxlen=lines)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                deque.append(line)
    except FileNotFoundError:
        return ""
    return "".join(deque)


@router.get("/logs/{filename}")
async def read_log_file(
    filename: str,
    lines: int = Query(default=500, ge=1, le=5000),
    _admin: User = Depends(require_admin),
) -> PlainTextResponse:
    """读取指定日志文件末尾 N 行（默认 500）。"""
    # 防路径穿越：只允许 logs/ 目录下名称符合规范的文件
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法文件名")
    log_dir = get_log_dir()
    path = os.path.realpath(os.path.join(log_dir, filename))
    if not path.startswith(os.path.realpath(log_dir) + os.sep):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法文件名")
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "日志文件不存在")
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, _tail_file, path, lines)
    return PlainTextResponse(content)
