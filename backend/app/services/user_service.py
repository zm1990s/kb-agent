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
_VERIFICATION_PIN_EXPIRE_MINUTES = 10
_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_DURATION_MINUTES = 15


class InvalidCredentialsError(Exception):
    """当前密码校验失败。"""


class DomainNotAllowedError(Exception):
    """邮箱域名不在白名单内。"""


class EmailExistsError(Exception):
    """邮箱已注册。"""


class EmailNotVerifiedError(Exception):
    """邮箱未验证，不允许登录。"""


class AccountLockedError(Exception):
    """账号因连续密码错误被暂时锁定。"""

    def __init__(self, remaining_seconds: int) -> None:
        self.remaining_seconds = remaining_seconds


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
    账号锁定时抛 AccountLockedError，邮箱未验证时抛 EmailNotVerifiedError。
    """
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    if not user.is_active:
        return None

    # 锁定检查（在密码校验之前，避免泄露账号是否存在）
    now = datetime.now(UTC)
    if user.locked_until is not None and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds())
        raise AccountLockedError(remaining)

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= _MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=_LOCKOUT_DURATION_MINUTES)
            logger.warning(
                "authenticate: 账号已锁定 email=%s until=%s", email, user.locked_until
            )
        await session.commit()
        return None

    # 密码正确：重置计数器（在 email_verified 检查之前，确保密码正确不受惩罚）
    if user.failed_login_attempts != 0 or user.locked_until is not None:
        user.failed_login_attempts = 0
        user.locked_until = None
        await session.commit()

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

    from app.services.settings_service import get_require_email_verification
    require_verification = await get_require_email_verification(session)

    token: str | None = None
    token_exp: datetime | None = None
    email_verified = True
    if require_verification:
        # 使用 6 位数字 PIN（10 分钟有效），代替链接方式，避免邮件系统拦截含链接的验证邮件
        token = f"{secrets.randbelow(1_000_000):06d}"
        token_exp = datetime.now(UTC) + timedelta(minutes=_VERIFICATION_PIN_EXPIRE_MINUTES)
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
        from app.services.email_service import send_verification_pin
        await send_verification_pin(email, token)
        logger.info("register: 验证 PIN 已发送 email=%s", email)

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


async def verify_email_pin(session: AsyncSession, *, email: str, pin: str) -> bool:
    """用 6 位 PIN 完成邮箱验证。PIN 无效、过期或邮箱不匹配返回 False，成功返回 True。"""
    user = await get_user_by_email(session, email)
    if user is None:
        return False
    if user.email_verified:
        return True
    if user.verification_token is None or user.verification_token != pin:
        return False
    if user.verification_token_exp is None or user.verification_token_exp < datetime.now(UTC):
        return False
    user.email_verified = True
    user.verification_token = None
    user.verification_token_exp = None
    await session.commit()
    logger.info("verify_email_pin: 邮箱验证成功 user_id=%s", user.id)
    return True


_RESET_CODE_EXPIRE_MINUTES = 10
_RESET_RATE_LIMIT_SECONDS = 60
_MAX_RESET_ATTEMPTS = 5


async def request_password_reset(session: AsyncSession, *, email: str) -> None:
    """触发密码重置：生成 6 位验证码并发送邮件。

    防护策略：
    - 无论邮箱是否存在，函数始终静默返回（不泄露用户存在性）
    - rate limit：同邮箱 1 次/分钟，超频则跳过发送
    - 验证码用 bcrypt 存储（与密码同等待遇）
    - 每次请求覆盖旧 token，旧码立即失效
    """
    # 延迟导入避免循环依赖
    from app.services.email_service import send_reset_code_email  # noqa: PLC0415

    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    now = datetime.now(UTC)
    if user.reset_rate_exp is not None and user.reset_rate_exp > now:
        return  # rate limit 未过，静默忽略

    code = f"{secrets.randbelow(1_000_000):06d}"
    user.reset_code_hash = hash_password(code)
    user.reset_code_exp = now + timedelta(minutes=_RESET_CODE_EXPIRE_MINUTES)
    user.reset_attempts = 0
    user.reset_rate_exp = now + timedelta(seconds=_RESET_RATE_LIMIT_SECONDS)
    await session.commit()

    await send_reset_code_email(email, code)
    logger.info("request_password_reset: 验证码已发送 user_id=%s", user.id)


async def reset_password_with_code(
    session: AsyncSession, *, email: str, code: str, new_password: str
) -> bool:
    """用验证码重置密码。失败（无效/过期/超次数）返回 False，成功返回 True。

    失败时不区分具体原因（防信息泄露）。
    """
    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return False

    now = datetime.now(UTC)
    if (
        user.reset_code_hash is None
        or user.reset_code_exp is None
        or user.reset_code_exp < now
    ):
        return False

    if user.reset_attempts >= _MAX_RESET_ATTEMPTS:
        return False

    if not verify_password(code, user.reset_code_hash):
        user.reset_attempts += 1
        await session.commit()
        return False

    user.password_hash = hash_password(new_password)
    user.reset_code_hash = None
    user.reset_code_exp = None
    user.reset_attempts = 0
    user.reset_rate_exp = None
    user.failed_login_attempts = 0
    user.locked_until = None
    await session.commit()
    logger.info("reset_password_with_code: 密码重置成功 user_id=%s", user.id)
    return True
