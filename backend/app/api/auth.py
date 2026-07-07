"""认证路由。api 层只做校验、调 service、映射错误到 HTTP，不写业务逻辑。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.auth import RegisterRequest, UserPublic
from app.services.user_service import (
    DomainNotAllowedError,
    EmailExistsError,
    register_user,
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
