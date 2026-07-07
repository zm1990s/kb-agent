"""空间业务逻辑：建空间、加成员、列出「我可见」的空间。

隔离核心：列表只返回当前用户是成员的空间（workspace_members），
Partner 看不到未授权空间。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User, Workspace, WorkspaceMember


class WorkspaceNotFoundError(Exception):
    """空间不存在。"""


class UserNotFoundError(Exception):
    """待加入的用户不存在。"""


class AlreadyMemberError(Exception):
    """用户已是该空间成员。"""


async def create_workspace(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    owner: User,
) -> Workspace:
    """建空间，并把创建者登记为 owner 成员。"""
    ws = Workspace(id=uuid.uuid4(), name=name, description=description)
    session.add(ws)
    session.add(
        WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role_in_ws="owner")
    )
    await session.commit()
    await session.refresh(ws)
    return ws


async def add_member(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role_in_ws: str,
) -> WorkspaceMember:
    """把用户加入空间。空间/用户不存在或已是成员分别抛对应异常。"""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise WorkspaceNotFoundError(str(workspace_id))

    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))

    existing = await session.get(WorkspaceMember, (workspace_id, user_id))
    if existing is not None:
        raise AlreadyMemberError(str(user_id))

    member = WorkspaceMember(
        workspace_id=workspace_id, user_id=user_id, role_in_ws=role_in_ws
    )
    session.add(member)
    await session.commit()
    return member


async def list_my_workspaces(
    session: AsyncSession, *, user: User
) -> list[tuple[Workspace, str]]:
    """列出当前用户是成员的空间，附带其在空间内的角色。"""
    stmt = (
        select(Workspace, WorkspaceMember.role_in_ws)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    result = await session.execute(stmt)
    return [(ws, role) for ws, role in result.all()]


async def is_member(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """当前用户是否为该空间成员（供 require_ws_member 使用）。"""
    member = await session.get(WorkspaceMember, (workspace_id, user_id))
    return member is not None
