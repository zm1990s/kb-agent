"""用户业务逻辑：注册（含域名白名单）、按邮箱查询。

安全要点（SECURITY #9）：域名白名单用**完整域名相等匹配**，不是 endswith，
避免 `user@fakecompany.com` 混入白名单 `company.com`。
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.auth import AllowedDomain, User

logger = logging.getLogger(__name__)

_VERIFICATION_TOKEN_EXPIRE_HOURS = 24


class InvalidCredentialsError(Exception):
    """当前密码校验失败。"""


class DomainNotAllowedError(Exception):
    """邮箱域名不在白名单内。"""


class EmailExistsError(Exception):
    """邮箱已注册。"""


class EmailNotVerifiedError(Exception):
    """邮箱未验证，不允许登录。"""


def _email_domain(email: str) -> str:
    """取邮箱 @ 之后的域名部分（小写）。"""
    return email.rsplit("@", 1)[-1].lower()


async def is_domain_allowed(session: AsyncSession, email: str) -> bool:
    """完整域名相等匹配 DB 白名单。白名单为空时拒绝所有（安全默认）。"""
    domain = _email_domain(email)
    result = await session.execute(
        select(AllowedDomain.id).where(AllowedDomain.domain == domain)
    )
    return result.scalar_one_or_none() is not None


async def list_allowed_domains(session: AsyncSession) -> list[AllowedDomain]:
    result = await session.execute(
        select(AllowedDomain).order_by(AllowedDomain.domain)
    )
    return list(result.scalars().all())


async def add_allowed_domain(session: AsyncSession, *, domain: str) -> AllowedDomain:
    """新增白名单域名（幂等：已存在则返回现有）。"""
    domain = domain.strip().lower()
    existing = await session.execute(
        select(AllowedDomain).where(AllowedDomain.domain == domain)
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found
    row = AllowedDomain(id=uuid.uuid4(), domain=domain)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def remove_allowed_domain(session: AsyncSession, *, domain_id: uuid.UUID) -> bool:
    row = await session.get(AllowedDomain, domain_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def change_password(
    session: AsyncSession, *, user: User, current_password: str, new_password: str
) -> None:
    """修改登录用户自己的密码。当前密码不符抛 InvalidCredentialsError。"""
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError()
    user.password_hash = hash_password(new_password)
    await session.commit()


async def seed_admin(session: AsyncSession) -> User | None:
    """按配置幂等创建首个管理员。

    读取 ADMIN_EMAIL / ADMIN_PASSWORD；已存在同邮箱用户则跳过（不覆盖密码，
    以免抹掉用户后续自行修改的密码）。密码以 bcrypt 存库。
    """
    settings = get_settings()
    email = settings.admin_email.strip().lower()
    password = settings.admin_password
    if not email or not password:
        return None

    existing = await get_user_by_email(session, email)
    if existing is not None:
        return existing  # 幂等：已存在则不动（尊重用户改过的密码）

    admin = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        role="admin",
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> User | None:
    """校验邮箱+密码，成功返回 User，失败返回 None（不区分邮箱不存在/密码错）。
    邮箱未验证时抛 EmailNotVerifiedError。
    """
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None

    # 仅当功能启用时才阻止未验证用户登录
    from app.services.settings_service import get_require_email_verification
    if await get_require_email_verification(session) and not user.email_verified:
        raise EmailNotVerifiedError(email)

    return user


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: str = "user",
) -> tuple["User", bool]:
    """注册新用户。域名不合法抛 DomainNotAllowedError，重复抛 EmailExistsError。
    返回 (user, email_verification_pending)。
    """
    email = email.lower()

    if not await is_domain_allowed(session, email):
        raise DomainNotAllowedError(email)

    if await get_user_by_email(session, email) is not None:
        raise EmailExistsError(email)

    from app.services.settings_service import (
        get_require_email_verification,
        get_site_base_url,
    )
    require_verification = await get_require_email_verification(session)

    token: str | None = None
    token_exp: datetime | None = None
    email_verified = True
    if require_verification:
        token = secrets.token_urlsafe(32)
        token_exp = datetime.now(UTC) + timedelta(hours=_VERIFICATION_TOKEN_EXPIRE_HOURS)
        email_verified = False

    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(password),
        role=role,
        email_verified=email_verified,
        verification_token=token,
        verification_token_exp=token_exp,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise EmailExistsError(email) from exc
    await session.refresh(user)

    # 注册时按规则自动入组
    from app.services.rbac_service import sync_user_groups

    await sync_user_groups(session, user=user)

    if require_verification and token:
        site_url = await get_site_base_url(session)
        verify_url = f"{site_url}/verify-email?token={token}"
        from app.services.email_service import send_verification_email
        await send_verification_email(email, verify_url)
        logger.info("register: 验证邮件已发送 email=%s", email)

    return user, require_verification


async def verify_email_token(session: AsyncSession, *, token: str) -> bool:
    """用验证 token 完成邮箱验证。token 无效或过期返回 False，成功返回 True。"""
    result = await session.execute(
        select(User).where(User.verification_token == token)
    )
    user = result.scalar_one_or_none()
    if user is None:
        return False
    if user.verification_token_exp is None or user.verification_token_exp < datetime.now(UTC):
        return False
    user.email_verified = True
    user.verification_token = None
    user.verification_token_exp = None
    await session.commit()
    logger.info("verify_email: 邮箱验证成功 user_id=%s", user.id)
    return True
