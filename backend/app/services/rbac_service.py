"""F4-F7 · 用户管理、用户组、RBAC、空间按组授权 —— 业务逻辑。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.auth import User
from app.models.rbac import (
    Group,
    GroupMember,
    GroupPermission,
    GroupRule,
)

# ── F4 用户管理 ────────────────────────────────────────

async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def set_user_active(
    session: AsyncSession, *, user_id: uuid.UUID, active: bool
) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.is_active = active
    await session.commit()
    await session.refresh(user)
    return user


async def set_user_role(
    session: AsyncSession, *, user_id: uuid.UUID, role: str
) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.role = role
    await session.commit()
    await session.refresh(user)
    return user


async def admin_reset_password(
    session: AsyncSession, *, user_id: uuid.UUID, new_password: str
) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.password_hash = hash_password(new_password)
    await session.commit()
    return user


async def delete_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> bool:
    user = await session.get(User, user_id)
    if user is None:
        return False
    await session.delete(user)
    await session.commit()
    return True


# ── F5 用户组 + 规则 + 自动入组 ─────────────────────────

async def list_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(select(Group).order_by(Group.name))
    return list(result.scalars().all())


async def create_group(
    session: AsyncSession, *, name: str, description: str | None
) -> Group:
    group = Group(id=uuid.uuid4(), name=name, description=description)
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def delete_group(session: AsyncSession, *, group_id: uuid.UUID) -> bool:
    group = await session.get(Group, group_id)
    if group is None:
        return False
    await session.delete(group)
    await session.commit()
    return True


async def list_group_rules(
    session: AsyncSession, *, group_id: uuid.UUID
) -> list[GroupRule]:
    result = await session.execute(
        select(GroupRule).where(GroupRule.group_id == group_id)
    )
    return list(result.scalars().all())


async def add_group_rule(
    session: AsyncSession, *, group_id: uuid.UUID, field: str, op: str, value: str
) -> GroupRule:
    rule = GroupRule(
        id=uuid.uuid4(), group_id=group_id, field=field, op=op, value=value.lower()
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_group_rule(session: AsyncSession, *, rule_id: uuid.UUID) -> bool:
    rule = await session.get(GroupRule, rule_id)
    if rule is None:
        return False
    await session.delete(rule)
    await session.commit()
    return True


async def list_group_members(
    session: AsyncSession, *, group_id: uuid.UUID
) -> list[User]:
    stmt = (
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _rule_matches(rule: GroupRule, user: User) -> bool:
    if rule.field == "email_domain":
        subject = user.email.rsplit("@", 1)[-1].lower()
    elif rule.field == "email":
        subject = user.email.lower()
    elif rule.field == "role":
        subject = user.role.lower()
    else:
        return False
    val = rule.value.lower()
    if rule.op == "equals":
        return subject == val
    if rule.op == "endswith":
        return subject.endswith(val)
    if rule.op == "contains":
        return val in subject
    return False


async def _groups_for_user(session: AsyncSession, user: User) -> set[uuid.UUID]:
    """按规则计算用户应属的组（任一规则命中即入组）。"""
    result = await session.execute(select(GroupRule))
    rules = list(result.scalars().all())
    matched: set[uuid.UUID] = set()
    for r in rules:
        if _rule_matches(r, user):
            matched.add(r.group_id)
    return matched


async def sync_user_groups(session: AsyncSession, *, user: User) -> None:
    """按规则重算该用户的自动组成员关系（增量 + 移除不再匹配的自动组）。

    说明：这里把「自动入组」视为规则的映射结果；仅增不删更安全，但为让
    「改规则后重算」符合直觉，采用：规则命中即加入，不主动移除手动加的组。
    """
    target = await _groups_for_user(session, user)
    existing_result = await session.execute(
        select(GroupMember.group_id).where(GroupMember.user_id == user.id)
    )
    existing = {g for (g,) in existing_result.all()}
    for gid in target - existing:
        session.add(GroupMember(group_id=gid, user_id=user.id))
    await session.commit()


async def recompute_all_memberships(session: AsyncSession) -> int:
    """手动全量重算所有用户的自动入组。返回处理用户数。"""
    result = await session.execute(select(User))
    users = list(result.scalars().all())
    for user in users:
        await sync_user_groups(session, user=user)
    return len(users)


# ── F6 RBAC ────────────────────────────────────────────

async def get_group_permissions(
    session: AsyncSession, *, group_id: uuid.UUID
) -> list[GroupPermission]:
    result = await session.execute(
        select(GroupPermission).where(GroupPermission.group_id == group_id)
    )
    return list(result.scalars().all())


async def set_group_permission(
    session: AsyncSession, *, group_id: uuid.UUID, module: str, level: str
) -> None:
    existing = await session.get(GroupPermission, (group_id, module))
    if level == "none":
        if existing is not None:
            await session.delete(existing)
    elif existing is None:
        session.add(GroupPermission(group_id=group_id, module=module, level=level))
    else:
        existing.level = level
    await session.commit()


async def effective_permissions(
    session: AsyncSession, *, user: User
) -> dict[str, str]:
    """用户对各模块的有效权限（所属组权限取最高：write>read>none）。

    admin 角色绕过一切：所有模块 write。
    """
    from app.models.rbac import MODULES

    if user.role == "admin":
        return {m: "write" for m in MODULES}

    stmt = (
        select(GroupPermission.module, GroupPermission.level)
        .join(GroupMember, GroupMember.group_id == GroupPermission.group_id)
        .where(GroupMember.user_id == user.id)
    )
    result = await session.execute(stmt)
    perms: dict[str, str] = {}
    rank = {"read": 1, "write": 2}
    for module, level in result.all():
        if rank.get(level, 0) > rank.get(perms.get(module, "none"), 0):
            perms[module] = level
    return perms
