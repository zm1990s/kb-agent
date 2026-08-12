"""管理员 SSO 配置 API。

端点（均需 admin）：
  GET  /admin/sso-settings          读取 SSO 开关
  PUT  /admin/sso-settings          设置 SSO 开关
  GET  /admin/sso-clients           列出所有允许的回调 URI 客户端
  POST /admin/sso-clients           新增客户端
  DELETE /admin/sso-clients/{id}    删除客户端
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_admin
from app.models.sso import SsoClient
from app.services.settings_service import SSO_ENABLED_KEY, get_setting, set_setting

router = APIRouter(
    prefix="/admin",
    tags=["admin-sso"],
    dependencies=[Depends(require_admin)],
)


# ── Schemas ──────────────────────────────────────────────


class SsoSettingsResponse(BaseModel):
    enabled: bool


class SsoSettingsUpdate(BaseModel):
    enabled: bool


class SsoClientCreate(BaseModel):
    uri_prefix: str
    description: str = ""


class SsoClientPublic(BaseModel):
    id: str
    uri_prefix: str
    description: str | None
    created_at: str

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────


@router.get("/sso-settings", response_model=SsoSettingsResponse)
async def get_sso_settings(session: AsyncSession = Depends(get_session)):
    val = await get_setting(session, SSO_ENABLED_KEY)
    return SsoSettingsResponse(enabled=val == "true")


@router.put("/sso-settings", response_model=SsoSettingsResponse)
async def update_sso_settings(
    body: SsoSettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    await set_setting(session, SSO_ENABLED_KEY, "true" if body.enabled else "false")
    return SsoSettingsResponse(enabled=body.enabled)


@router.get("/sso-clients", response_model=list[SsoClientPublic])
async def list_sso_clients(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(SsoClient).order_by(SsoClient.created_at.asc())
    )
    clients = result.scalars().all()
    return [
        SsoClientPublic(
            id=str(c.id),
            uri_prefix=c.uri_prefix,
            description=c.description,
            created_at=c.created_at.isoformat(),
        )
        for c in clients
    ]


@router.post("/sso-clients", response_model=SsoClientPublic, status_code=status.HTTP_201_CREATED)
async def create_sso_client(
    body: SsoClientCreate,
    session: AsyncSession = Depends(get_session),
):
    uri = body.uri_prefix.strip().rstrip("/")
    if not uri.startswith(("http://", "https://")):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uri_prefix 必须以 http:// 或 https:// 开头",
        )

    # 重复检查
    existing = await session.execute(
        select(SsoClient).where(SsoClient.uri_prefix == uri)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="该 URI 前缀已存在",
        )

    client = SsoClient(
        id=uuid.uuid4(),
        uri_prefix=uri,
        description=body.description.strip() or None,
    )
    session.add(client)
    await session.commit()
    await session.refresh(client)

    return SsoClientPublic(
        id=str(client.id),
        uri_prefix=client.uri_prefix,
        description=client.description,
        created_at=client.created_at.isoformat(),
    )


@router.delete("/sso-clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sso_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    client = await session.get(SsoClient, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="客户端不存在")
    await session.delete(client)
    await session.commit()


