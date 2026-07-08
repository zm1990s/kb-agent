"""目录（文件夹）路由。空间成员可维护；workspace 经 query/body 传入。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.schemas.document import (
    FolderCreate,
    FolderMove,
    FolderPublic,
    FolderRename,
)
from app.services.folder_service import (
    FolderCycleError,
    ParentFolderInvalidError,
    create_folder,
    delete_folder,
    get_folder_in_workspace,
    list_folders,
    move_folder,
    rename_folder,
)
from app.services.workspace_service import is_member

router = APIRouter(prefix="/folders", tags=["folders"])


async def _ensure_member(session: AsyncSession, ws_id: uuid.UUID, user: User) -> None:
    if not await is_member(session, workspace_id=ws_id, user_id=user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该空间")


@router.get("", response_model=list[FolderPublic])
async def list_ws_folders(
    workspace: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[FolderPublic]:
    await _ensure_member(session, workspace, current_user)
    folders = await list_folders(session, workspace_id=workspace)
    return [FolderPublic.model_validate(f) for f in folders]


@router.post("", response_model=FolderPublic, status_code=status.HTTP_201_CREATED)
async def create_ws_folder(
    body: FolderCreate,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FolderPublic:
    await _ensure_member(session, workspace_id, current_user)
    try:
        folder = await create_folder(
            session,
            workspace_id=workspace_id,
            name=body.name,
            parent_id=body.parent_id,
        )
    except ParentFolderInvalidError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "父目录不存在或不属于该空间"
        ) from exc
    return FolderPublic.model_validate(folder)


@router.patch("/{folder_id}", response_model=FolderPublic)
async def rename_ws_folder(
    folder_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: FolderRename,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FolderPublic:
    await _ensure_member(session, workspace_id, current_user)
    folder = await get_folder_in_workspace(
        session, folder_id=folder_id, workspace_id=workspace_id
    )
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目录不存在")
    folder = await rename_folder(session, folder=folder, name=body.name)
    return FolderPublic.model_validate(folder)


@router.patch("/{folder_id}/move", response_model=FolderPublic)
async def move_ws_folder(
    folder_id: uuid.UUID,
    workspace_id: uuid.UUID,
    body: FolderMove,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FolderPublic:
    await _ensure_member(session, workspace_id, current_user)
    folder = await get_folder_in_workspace(
        session, folder_id=folder_id, workspace_id=workspace_id
    )
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目录不存在")
    try:
        folder = await move_folder(session, folder=folder, new_parent_id=body.parent_id)
    except FolderCycleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能移动到自身或子目录下") from exc
    except ParentFolderInvalidError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目标父目录无效") from exc
    return FolderPublic.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ws_folder(
    folder_id: uuid.UUID,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _ensure_member(session, workspace_id, current_user)
    folder = await get_folder_in_workspace(
        session, folder_id=folder_id, workspace_id=workspace_id
    )
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "目录不存在")
    await delete_folder(session, folder=folder)
