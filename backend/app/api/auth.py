"""认证路由。api 层只做校验、调 service、映射错误到 HTTP，不写业务逻辑。"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, get_session
from app.core.deps import get_current_user, require_admin
from app.core.security import create_access_token
from app.models.auth import User
from app.schemas.auth import (
    AllowedDomainCreate,
    AllowedDomainPublic,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)
from app.services.rbac_service import delete_user
from app.services.usage_service import record_event
from app.services.user_service import (
    AccountLockedError,
    DomainNotAllowedError,
    EmailExistsError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    add_allowed_domain,
    authenticate,
    change_password,
    list_allowed_domains,
    register_user,
    remove_allowed_domain,
    request_password_reset,
    reset_password_with_code,
    verify_email_pin,
    verify_email_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    try:
        user, pending = await register_user(
            session, email=body.email, password=body.password
        )
    except DomainNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="邮箱域名不在允许列表内",
        ) from exc
    except EmailExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已注册",
        ) from exc
    resp = RegisterResponse.model_validate(user)
    resp.email_verification_pending = pending
    return resp


@router.get("/verify-email")
async def verify_email(
    token: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """验证邮箱 token（旧链接方式，保持兼容）；无效或过期返回 400。"""
    ok = await verify_email_token(session, token=token)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证链接无效或已过期",
        )
    return {"message": "ok"}


class VerifyPinRequest(BaseModel):
    email: EmailStr
    pin: str = Field(min_length=6, max_length=6)


@router.post("/verify-email-pin", status_code=status.HTTP_200_OK)
async def verify_email_by_pin(
    body: VerifyPinRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """用 6 位 PIN 完成邮箱验证；无效或过期返回 400。"""
    ok = await verify_email_pin(session, email=body.email, pin=body.pin)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_or_expired",
        )
    return {"message": "ok"}


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        user = await authenticate(session, email=body.email, password=body.password)
    except AccountLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"code": "account_locked", "remaining_seconds": exc.remaining_seconds},
        ) from exc
    except EmailNotVerifiedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
        ) from exc
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    token = create_access_token(user_id=user.id, role=user.role)

    async def _log() -> None:
        async with SessionLocal() as s:
            await record_event(s, action="login", user_id=user.id)

    background_tasks.add_task(_log)
    return TokenResponse(access_token=token, role=user.role)


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.get("/my-permissions")
async def my_permissions(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """当前用户对各模块的有效权限（admin 全 write；否则取所属组权限并集最高）。"""
    from app.services.rbac_service import effective_permissions

    return await effective_permissions(session, user=current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_own_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await change_password(
            session,
            user=current_user,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        ) from exc


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_self(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """用户主动注销账号（永久删除）。"""
    if current_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="管理员账号不可自助注销，请联系其他管理员操作",
        )
    await delete_user(session, user_id=current_user.id)


# ── 注册域名白名单（管理员维护）────────────────────────────


@router.get("/allowed-domains", response_model=list[AllowedDomainPublic])
async def get_allowed_domains(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AllowedDomainPublic]:
    rows = await list_allowed_domains(session)
    return [AllowedDomainPublic.model_validate(r) for r in rows]


@router.post(
    "/allowed-domains",
    response_model=AllowedDomainPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_allowed_domain(
    body: AllowedDomainCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AllowedDomainPublic:
    row = await add_allowed_domain(session, domain=body.domain)
    logger.info("audit admin add_allowed_domain admin=%s domain=%s", admin.id, body.domain)
    await record_event(session, action="admin_add_allowed_domain", user_id=admin.id,
                       meta={"domain": body.domain})
    return AllowedDomainPublic.model_validate(row)


@router.delete(
    "/allowed-domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_allowed_domain(
    domain_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    ok = await remove_allowed_domain(session, domain_id=domain_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "域名不存在")
    logger.info("audit admin remove_allowed_domain admin=%s domain_id=%s", admin.id, domain_id)
    await record_event(session, action="admin_remove_allowed_domain", user_id=admin.id,
                       meta={"domain_id": str(domain_id)})


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    body: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await request_password_reset(session, email=body.email)
    return {"message": "if_exists_sent"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    ok = await reset_password_with_code(
        session, email=body.email, code=body.code, new_password=body.new_password
    )
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_or_expired")
    return {"message": "password_reset_ok"}
