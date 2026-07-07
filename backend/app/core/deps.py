"""鉴权依赖。M1-U4 提供 get_current_user；M1-U5 在此扩展 require_admin 等。"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import TokenError, decode_access_token
from app.models.auth import User
from app.services.user_service import get_user_by_id

_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未认证或凭据无效",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """从 Bearer JWT 解析当前用户；无 token / 无效 / 用户不存在均返 401。"""
    if creds is None:
        raise _UNAUTHENTICATED
    try:
        payload = decode_access_token(creds.credentials)
    except TokenError as exc:
        raise _UNAUTHENTICATED from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise _UNAUTHENTICATED from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise _UNAUTHENTICATED
    return user


# require_auth 是 get_current_user 的语义别名（任何已认证用户）。
require_auth = get_current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """要求全局管理员角色；非管理员返 403。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


async def require_ws_member(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    """要求当前用户是路径中 workspace_id 所指空间的成员；否则 403。

    这是 workspace 隔离/越权校验（SECURITY #4）的通用地基：
    M2 文档等空间资源端点挂此依赖即可强制成员校验。
    管理员不自动获得所有空间访问权——需显式加入成员。
    """
    from app.services.workspace_service import is_member

    ok = await is_member(
        session, workspace_id=workspace_id, user_id=current_user.id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该空间",
        )
    return current_user
