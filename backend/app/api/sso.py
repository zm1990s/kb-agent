"""SSO 联合登录 API。

端点：
  GET  /sso/status      无需认证，返回 SSO 功能开关状态
  POST /sso/authorize   需要登录用户，校验 redirect_uri 白名单，签发一次性 code
  POST /sso/token       外部应用后端调用，code 换用户信息
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.security import hash_token
from app.models.auth import User
from app.models.rbac import Group, GroupMember
from app.models.sso import SsoClient, SsoCode
from app.services.settings_service import SSO_ENABLED_KEY, get_setting

router = APIRouter(prefix="/sso", tags=["sso"])

# 授权码有效期（秒）
_CODE_TTL_SEC = 60


# ── Schemas ──────────────────────────────────────────────


class AuthorizeRequest(BaseModel):
    redirect_uri: str
    state: str = ""


class AuthorizeResponse(BaseModel):
    code: str
    redirect_uri: str
    state: str


class TokenRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    id: str
    email: str
    role: str
    groups: list[str]


class StatusResponse(BaseModel):
    enabled: bool


# ── Helpers ──────────────────────────────────────────────


async def _sso_enabled(session: AsyncSession) -> bool:
    val = await get_setting(session, SSO_ENABLED_KEY)
    return val == "true"


async def _get_user_groups(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """返回用户所属的所有组名列表。"""
    result = await session.execute(
        select(Group.name)
        .join(GroupMember, Group.id == GroupMember.group_id)
        .where(GroupMember.user_id == user_id)
        .order_by(Group.name)
    )
    return [row for (row,) in result.all()]


# ── Endpoints ────────────────────────────────────────────


@router.get("/status", response_model=StatusResponse)
async def sso_status(session: AsyncSession = Depends(get_session)):
    """返回 SSO 功能是否已启用（无需认证，供登录页判断）。"""
    return StatusResponse(enabled=await _sso_enabled(session))


@router.post("/authorize", response_model=AuthorizeResponse)
async def sso_authorize(
    body: AuthorizeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """为已登录用户签发一次性 SSO 授权码。

    安全要点：
    - 需要有效的 Bearer JWT（get_current_user 依赖）
    - redirect_uri 必须以某个已登记的 SsoClient.uri_prefix 为前缀
    - code 只存 SHA-256 hash，明文仅在此响应中返回一次
    - TTL 60s
    """
    if not await _sso_enabled(session):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="sso_disabled")

    # 校验 redirect_uri 白名单（前缀匹配）
    result = await session.execute(select(SsoClient))
    clients = result.scalars().all()
    allowed = any(body.redirect_uri.startswith(c.uri_prefix) for c in clients)
    if not allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="redirect_uri_not_allowed",
        )

    # 生成授权码
    code = secrets.token_urlsafe(32)
    code_hash = hash_token(code)
    expires_at = datetime.now(UTC) + timedelta(seconds=_CODE_TTL_SEC)

    session.add(
        SsoCode(
            id=uuid.uuid4(),
            code_hash=code_hash,
            user_id=current_user.id,
            redirect_uri=body.redirect_uri,
            expires_at=expires_at,
        )
    )
    await session.commit()

    return AuthorizeResponse(
        code=code,
        redirect_uri=body.redirect_uri,
        state=body.state,
    )


@router.post("/token", response_model=TokenResponse)
async def sso_token(
    body: TokenRequest,
    session: AsyncSession = Depends(get_session),
):
    """用一次性 code 换取用户信息（由外部应用后端调用）。

    安全要点：
    - code 一次性（used_at 非空即拒绝）
    - code 过期即拒绝
    - 返回前校验用户仍为活跃状态
    """
    if not await _sso_enabled(session):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="sso_disabled")

    code_hash = hash_token(body.code)
    result = await session.execute(
        select(SsoCode).where(SsoCode.code_hash == code_hash)
    )
    sso_code = result.scalar_one_or_none()

    if sso_code is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_code")

    if sso_code.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="code_already_used")

    if datetime.now(UTC) > sso_code.expires_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="code_expired")

    # 标记已使用
    sso_code.used_at = datetime.now(UTC)
    await session.flush()

    user = await session.get(User, sso_code.user_id)
    if user is None or not user.is_active:
        await session.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="user_inactive")

    groups = await _get_user_groups(session, user.id)
    await session.commit()

    return TokenResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        groups=groups,
    )
