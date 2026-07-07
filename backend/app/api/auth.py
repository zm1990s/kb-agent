"""认证路由。api 层只做校验、调 service、映射错误到 HTTP，不写业务逻辑。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.core.security import create_access_token
from app.models.auth import User
from app.schemas.auth import (
    AllowedDomainCreate,
    AllowedDomainPublic,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)
from app.services.user_service import (
    DomainNotAllowedError,
    EmailExistsError,
    InvalidCredentialsError,
    add_allowed_domain,
    authenticate,
    change_password,
    list_allowed_domains,
    register_user,
    remove_allowed_domain,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> UserPublic:
    try:
        user = await register_user(
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
    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await authenticate(session, email=body.email, password=body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    token = create_access_token(user_id=user.id, role=user.role)
    return TokenResponse(access_token=token, role=user.role)


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


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
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AllowedDomainPublic:
    row = await add_allowed_domain(session, domain=body.domain)
    return AllowedDomainPublic.model_validate(row)


@router.delete(
    "/allowed-domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_allowed_domain(
    domain_id: uuid.UUID,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    ok = await remove_allowed_domain(session, domain_id=domain_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "域名不存在")
