"""分类路由。分类体系由管理员维护（require_admin），且须为该空间成员。

workspace 以 query/body 传入（非路径），故在端点内显式做成员校验。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.schemas.document import CategoryCreate, CategoryPublic
from app.services.category_service import (
    ParentCategoryInvalidError,
    create_category,
    list_categories,
)
from app.services.workspace_service import is_member

router = APIRouter(prefix="/categories", tags=["categories"])


async def _ensure_member(session: AsyncSession, ws_id: uuid.UUID, user: User) -> None:
    if not await is_member(session, workspace_id=ws_id, user_id=user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")


@router.get("", response_model=list[CategoryPublic])
async def list_ws_categories(
    workspace: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryPublic]:
    await _ensure_member(session, workspace, current_user)
    cats = await list_categories(session, workspace_id=workspace)
    return [CategoryPublic.model_validate(c) for c in cats]


@router.post("", response_model=CategoryPublic, status_code=status.HTTP_201_CREATED)
async def create_ws_category(
    body: CategoryCreate,
    workspace_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CategoryPublic:
    await _ensure_member(session, workspace_id, current_user)
    try:
        cat = await create_category(
            session,
            workspace_id=workspace_id,
            name=body.name,
            parent_id=body.parent_id,
        )
    except ParentCategoryInvalidError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "父分类不存在或不属于该空间"
        ) from exc
    return CategoryPublic.model_validate(cat)
