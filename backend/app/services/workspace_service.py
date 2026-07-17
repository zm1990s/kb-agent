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
    user_id: uuid.UUID | None = None,
    email: str | None = None,
    role_in_ws: str,
) -> WorkspaceMember:
    """把用户加入空间。可按 user_id 或 email 查找用户。"""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise WorkspaceNotFoundError(str(workspace_id))

    if user_id is not None:
        user = await session.get(User, user_id)
    elif email is not None:
        result = await session.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
    else:
        raise UserNotFoundError("必须提供 user_id 或 email")

    if user is None:
        raise UserNotFoundError(str(user_id or email))

    user_id = user.id

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
    """列出当前用户可见的空间（admin 看全部；普通用户：个人成员 ∪ 所属组被授权），附带空间内角色。"""
    from app.models.rbac import GroupMember, WorkspaceGroupGrant

    # admin 可见全部空间，角色标为 owner
    if user.role == "admin":
        result = await session.execute(select(Workspace))
        return [(ws, "owner") for ws in result.scalars().all()]

    seen: dict[uuid.UUID, tuple[Workspace, str]] = {}

    # 个人成员
    direct = await session.execute(
        select(Workspace, WorkspaceMember.role_in_ws)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    )
    for ws, role in direct.all():
        seen[ws.id] = (ws, role)

    # 组授权（个人成员已存在则不覆盖）
    via_group = await session.execute(
        select(Workspace, WorkspaceGroupGrant.role_in_ws)
        .join(WorkspaceGroupGrant, WorkspaceGroupGrant.workspace_id == Workspace.id)
        .join(GroupMember, GroupMember.group_id == WorkspaceGroupGrant.group_id)
        .where(GroupMember.user_id == user.id)
    )
    for ws, role in via_group.all():
        seen.setdefault(ws.id, (ws, role))

    return list(seen.values())


async def grant_group(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    group_id: uuid.UUID,
    role_in_ws: str,
):
    """把空间授权给某个组（幂等 upsert）。"""
    from app.models.rbac import WorkspaceGroupGrant

    grant = await session.get(WorkspaceGroupGrant, (workspace_id, group_id))
    if grant is None:
        grant = WorkspaceGroupGrant(
            workspace_id=workspace_id, group_id=group_id, role_in_ws=role_in_ws
        )
        session.add(grant)
    else:
        grant.role_in_ws = role_in_ws
    await session.commit()
    return grant


async def revoke_group(
    session: AsyncSession, *, workspace_id: uuid.UUID, group_id: uuid.UUID
) -> bool:
    from app.models.rbac import WorkspaceGroupGrant

    grant = await session.get(WorkspaceGroupGrant, (workspace_id, group_id))
    if grant is None:
        return False
    await session.delete(grant)
    await session.commit()
    return True


async def list_group_grants(session: AsyncSession, *, workspace_id: uuid.UUID):
    from app.models.rbac import WorkspaceGroupGrant

    result = await session.execute(
        select(WorkspaceGroupGrant).where(
            WorkspaceGroupGrant.workspace_id == workspace_id
        )
    )
    return list(result.scalars().all())


async def is_member(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """当前用户是否有该空间访问权：admin 全绕过；个人成员 ∪ 所属组被授权（F7）。"""
    user = await session.get(User, user_id)
    if user is not None and user.role == "admin":
        return True
    member = await session.get(WorkspaceMember, (workspace_id, user_id))
    if member is not None:
        return True
    # 通过所属组的空间授权获得访问权
    from app.models.rbac import GroupMember, WorkspaceGroupGrant

    stmt = (
        select(WorkspaceGroupGrant.group_id)
        .join(GroupMember, GroupMember.group_id == WorkspaceGroupGrant.group_id)
        .where(
            WorkspaceGroupGrant.workspace_id == workspace_id,
            GroupMember.user_id == user_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first() is not None


async def get_ws_role(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> str | None:
    """返回用户在该空间内的有效角色（owner/editor/viewer），不是成员返回 None。

    优先级：全局 admin → 个人成员角色 → 组授权角色（取最高权限）。
    角色优先级：owner > editor > viewer。
    """
    from app.models.rbac import GroupMember, WorkspaceGroupGrant

    _rank = {"owner": 3, "editor": 2, "viewer": 1}

    user = await session.get(User, user_id)
    if user is not None and user.role == "admin":
        return "owner"

    best: str | None = None

    member = await session.get(WorkspaceMember, (workspace_id, user_id))
    if member is not None:
        best = member.role_in_ws

    # 组授权
    stmt = (
        select(WorkspaceGroupGrant.role_in_ws)
        .join(GroupMember, GroupMember.group_id == WorkspaceGroupGrant.group_id)
        .where(
            WorkspaceGroupGrant.workspace_id == workspace_id,
            GroupMember.user_id == user_id,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    for role in rows:
        if best is None or _rank.get(role, 0) > _rank.get(best, 0):
            best = role

    return best
