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
