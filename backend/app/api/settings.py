"""系统设置路由（管理员）。当前含引擎（LLM 后端）选择。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_admin
from app.models.auth import User
from app.services.settings_service import (
    ENGINE_CATALOG,
    EngineNotAvailableError,
    get_engine_backend,
    set_engine_backend,
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
