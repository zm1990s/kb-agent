"""目录（文件夹）业务逻辑：用户手动维护的层级目录树。

隔离：文件夹隶属 workspace；所有操作带 workspace 约束。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Folder


class FolderNotFoundError(Exception):
    """文件夹不存在或不属于该空间。"""


class ParentFolderInvalidError(Exception):
    """父文件夹不存在或跨空间。"""


async def create_folder(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    parent_id: uuid.UUID | None,
) -> Folder:
    if parent_id is not None:
        parent = await session.get(Folder, parent_id)
        if parent is None or parent.workspace_id != workspace_id:
            raise ParentFolderInvalidError(str(parent_id))
    folder = Folder(
        id=uuid.uuid4(), workspace_id=workspace_id, name=name, parent_id=parent_id
    )
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    return folder


async def list_folders(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[Folder]:
    stmt = (
        select(Folder)
        .where(Folder.workspace_id == workspace_id)
        .order_by(Folder.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_folder_in_workspace(
    session: AsyncSession, *, folder_id: uuid.UUID, workspace_id: uuid.UUID
) -> Folder | None:
    folder = await session.get(Folder, folder_id)
    if folder is None or folder.workspace_id != workspace_id:
        return None
    return folder


async def rename_folder(
    session: AsyncSession, *, folder: Folder, name: str
) -> Folder:
    folder.name = name
    await session.commit()
    await session.refresh(folder)
    return folder


async def delete_folder(session: AsyncSession, *, folder: Folder) -> None:
    """删除文件夹（子文件夹级联删；其下文档 folder_id 由 DB 置空，不删文档）。"""
    await session.delete(folder)
    await session.commit()
