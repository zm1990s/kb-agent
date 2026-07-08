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


class FolderCycleError(Exception):
    """把目录移动到自己或其后代之下，会形成环。"""


async def move_folder(
    session: AsyncSession,
    *,
    folder: Folder,
    new_parent_id: uuid.UUID | None,
) -> Folder:
    """移动目录到新父级（new_parent_id=None 表示置为顶级）。防环。"""
    if new_parent_id is not None:
        if new_parent_id == folder.id:
            raise FolderCycleError("不能移动到自身")
        parent = await session.get(Folder, new_parent_id)
        if parent is None or parent.workspace_id != folder.workspace_id:
            raise ParentFolderInvalidError(str(new_parent_id))
        # 沿新父级向上回溯，若遇到自己则成环
        cursor: Folder | None = parent
        while cursor is not None:
            if cursor.parent_id == folder.id:
                raise FolderCycleError("不能移动到自己的子目录下")
            cursor = (
                await session.get(Folder, cursor.parent_id)
                if cursor.parent_id
                else None
            )
    folder.parent_id = new_parent_id
    await session.commit()
    await session.refresh(folder)
    return folder


async def delete_folder(session: AsyncSession, *, folder: Folder) -> None:
    """删除文件夹（子文件夹级联删；其下文档 folder_id 由 DB 置空，不删文档）。"""
    await session.delete(folder)
    await session.commit()
