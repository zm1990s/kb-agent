"""管理后台路由（F4-F6）：用户管理、用户组、RBAC。均需 admin。"""

import collections
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
from app.services.usage_service import get_stats

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


@router.patch("/users/{user_id}/active", response_model=UserAdminView)
async def set_active(
    user_id: uuid.UUID,
    body: SetActiveRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await rbac_service.set_user_active(
        session, user_id=user_id, active=body.is_active
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return user


@router.patch("/users/{user_id}/role", response_model=UserAdminView)
async def set_role(
    user_id: uuid.UUID,
    body: SetRoleRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await rbac_service.set_user_role(session, user_id=user_id, role=body.role)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return user


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    user = await rbac_service.admin_reset_password(
        session, user_id=user_id, new_password=body.new_password
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")


# ── F5 用户组 ──────────────────────────────────────────

@router.get("/groups", response_model=list[GroupPublic])
async def list_groups(session: AsyncSession = Depends(get_session)):
    return await rbac_service.list_groups(session)


@router.post("/groups", response_model=GroupPublic, status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, session: AsyncSession = Depends(get_session)):
    return await rbac_service.create_group(
        session, name=body.name, description=body.description
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    if not await rbac_service.delete_group(session, group_id=group_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "组不存在")


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
    session: AsyncSession = Depends(get_session),
):
    return await rbac_service.add_group_rule(
        session, group_id=group_id, field=body.field, op=body.op, value=body.value
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    if not await rbac_service.delete_group_rule(session, rule_id=rule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")


@router.get("/groups/{group_id}/members", response_model=list[UserAdminView])
async def group_members(
    group_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    return await rbac_service.list_group_members(session, group_id=group_id)


@router.post("/recompute-memberships")
async def recompute_memberships(session: AsyncSession = Depends(get_session)):
    count = await rbac_service.recompute_all_memberships(session)
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
    session: AsyncSession = Depends(get_session),
):
    await rbac_service.set_group_permission(
        session, group_id=group_id, module=body.module, level=body.level
    )


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
    days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """近 N 天用量统计：按天+动作聚合、活跃用户、总计。"""
    if days < 1 or days > 365:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "days 须在 1-365 之间")
    return await get_stats(session, days=days)


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
    content = _tail_file(path, lines)
    return PlainTextResponse(content)
