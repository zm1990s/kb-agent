"""空间路由。建空间/加成员需管理员；列表返回当前用户可见空间。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.schemas.auth import (
    MemberAddRequest,
    WorkspaceCreate,
    WorkspacePublic,
    WorkspaceWithRole,
)
from app.services.workspace_service import (
    AlreadyMemberError,
    UserNotFoundError,
    WorkspaceNotFoundError,
    add_member,
    create_workspace,
    grant_group,
    list_group_grants,
    list_my_workspaces,
    revoke_group,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspacePublic, status_code=status.HTTP_201_CREATED)
async def create(
    body: WorkspaceCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WorkspacePublic:
    ws = await create_workspace(
        session, name=body.name, description=body.description, owner=admin
    )
    return WorkspacePublic.model_validate(ws)


@router.get("", response_model=list[WorkspaceWithRole])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[WorkspaceWithRole]:
    rows = await list_my_workspaces(session, user=current_user)
    return [
        WorkspaceWithRole(
            id=ws.id,
            name=ws.name,
            description=ws.description,
            created_at=ws.created_at,
            role_in_ws=role,
        )
        for ws, role in rows
    ]


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
async def add_workspace_member(
    workspace_id: uuid.UUID,
    body: MemberAddRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await add_member(
            session,
            workspace_id=workspace_id,
            user_id=body.user_id,
            role_in_ws=body.role_in_ws,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "空间不存在") from exc
    except UserNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在") from exc
    except AlreadyMemberError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户已是该空间成员") from exc
    return {"status": "ok"}


# ── F7 空间按组授权 ────────────────────────────────────

class GroupGrantRequest(BaseModel):
    group_id: uuid.UUID
    role_in_ws: str


class GroupGrantPublic(BaseModel):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    role_in_ws: str

    model_config = {"from_attributes": True}


@router.get("/{workspace_id}/group-grants", response_model=list[GroupGrantPublic])
async def list_ws_group_grants(
    workspace_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[GroupGrantPublic]:
    grants = await list_group_grants(session, workspace_id=workspace_id)
    return [GroupGrantPublic.model_validate(g) for g in grants]


@router.post("/{workspace_id}/group-grants", status_code=status.HTTP_201_CREATED)
async def grant_ws_to_group(
    workspace_id: uuid.UUID,
    body: GroupGrantRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if body.role_in_ws not in ("owner", "editor", "viewer"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法角色")
    await grant_group(
        session,
        workspace_id=workspace_id,
        group_id=body.group_id,
        role_in_ws=body.role_in_ws,
    )
    return {"status": "ok"}


@router.delete(
    "/{workspace_id}/group-grants/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_ws_from_group(
    workspace_id: uuid.UUID,
    group_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await revoke_group(
        session, workspace_id=workspace_id, group_id=group_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授权不存在")
