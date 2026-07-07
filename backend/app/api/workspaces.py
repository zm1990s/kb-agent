"""空间路由。建空间/加成员需管理员；列表返回当前用户可见空间。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
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
    list_my_workspaces,
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
