"""用户业务逻辑：注册（含域名白名单）、按邮箱查询。

安全要点（SECURITY #9）：域名白名单用**完整域名相等匹配**，不是 endswith，
避免 `user@fakecompany.com` 混入白名单 `company.com`。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.auth import User


class DomainNotAllowedError(Exception):
    """邮箱域名不在白名单内。"""


class EmailExistsError(Exception):
    """邮箱已注册。"""


def _email_domain(email: str) -> str:
    """取邮箱 @ 之后的域名部分（小写）。"""
    return email.rsplit("@", 1)[-1].lower()


def is_domain_allowed(email: str) -> bool:
    """完整域名相等匹配白名单。白名单为空时拒绝所有（安全默认）。"""
    allowed = get_settings().allowed_email_domains_set
    if not allowed:
        return False
    return _email_domain(email) in allowed


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> User | None:
    """校验邮箱+密码，成功返回 User，失败返回 None（不区分邮箱不存在/密码错）。"""
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: str = "internal",
) -> User:
    """注册新用户。域名不合法抛 DomainNotAllowedError，重复抛 EmailExistsError。"""
    email = email.lower()

    if not is_domain_allowed(email):
        raise DomainNotAllowedError(email)

    if await get_user_by_email(session, email) is not None:
        raise EmailExistsError(email)

    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
