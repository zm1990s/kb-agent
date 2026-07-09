"""系统设置路由（管理员）。当前含引擎（LLM 后端）选择和平台品牌配置。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.services.settings_service import (
    ENGINE_CATALOG,
    EngineNotAvailableError,
    get_engine_backend,
    get_setting,
    set_engine_backend,
    set_setting,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class EngineOptionOut(BaseModel):
    id: str
    label: str
    available: bool


class EngineConfigOut(BaseModel):
    current: str
    options: list[EngineOptionOut]


class EngineConfigIn(BaseModel):
    backend: str


@router.get("/engine", response_model=EngineConfigOut)
async def get_engine_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EngineConfigOut:
    current = await get_engine_backend(session)
    return EngineConfigOut(
        current=current,
        options=[
            EngineOptionOut(id=e.id, label=e.label, available=e.available)
            for e in ENGINE_CATALOG
        ],
    )


@router.put("/engine", response_model=EngineConfigOut)
async def update_engine_config(
    body: EngineConfigIn,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EngineConfigOut:
    try:
        await set_engine_backend(session, body.backend)
    except EngineNotAvailableError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "该引擎不可用或未实现"
        ) from exc
    current = await get_engine_backend(session)
    return EngineConfigOut(
        current=current,
        options=[
            EngineOptionOut(id=e.id, label=e.label, available=e.available)
            for e in ENGINE_CATALOG
        ],
    )


# ── 平台品牌配置 ────────────────────────────────────────────


class BrandingOut(BaseModel):
    name: str
    logo_url: str


class BrandingIn(BaseModel):
    name: str | None = None
    logo_url: str | None = None


BRANDING_NAME_KEY = "branding_name"
BRANDING_LOGO_KEY = "branding_logo_url"
DEFAULT_NAME = "KB-Agent"
DEFAULT_LOGO = ""


@router.get("/branding", response_model=BrandingOut)
async def get_branding(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    """任意登录用户可读（NavBar 用）。"""
    name = await get_setting(session, BRANDING_NAME_KEY) or DEFAULT_NAME
    logo_url = await get_setting(session, BRANDING_LOGO_KEY) or DEFAULT_LOGO
    return BrandingOut(name=name, logo_url=logo_url)


@router.put("/branding", response_model=BrandingOut)
async def update_branding(
    body: BrandingIn,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    if body.name is not None:
        await set_setting(session, BRANDING_NAME_KEY, body.name.strip() or DEFAULT_NAME)
    if body.logo_url is not None:
        await set_setting(session, BRANDING_LOGO_KEY, body.logo_url.strip())
    name = await get_setting(session, BRANDING_NAME_KEY) or DEFAULT_NAME
    logo_url = await get_setting(session, BRANDING_LOGO_KEY) or DEFAULT_LOGO
    return BrandingOut(name=name, logo_url=logo_url)
