"""F4-F7：用户管理 / 用户组 / RBAC / 空间按组授权。"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ── F4 用户管理 ────────────────────────────────────────

async def test_admin_lists_and_manages_users(client, seed_user, seed_domain):
    _, admin = await seed_user("admin")
    # 造一个普通用户
    await seed_domain("company.com")
    reg = await client.post(
        "/auth/register", json={"email": "u1@company.com", "password": "longenough1"}
    )
    uid = reg.json()["id"]

    # 列表含该用户
    users = await client.get("/admin/users", headers=admin)
    assert users.status_code == 200
    assert any(u["id"] == uid for u in users.json())

    # 禁用 → 无法登录
    dis = await client.patch(
        f"/admin/users/{uid}/active", json={"is_active": False}, headers=admin
    )
    assert dis.status_code == 200 and dis.json()["is_active"] is False
    login = await client.post(
        "/auth/login", json={"email": "u1@company.com", "password": "longenough1"}
    )
    assert login.status_code == 401

    # 重置密码 → 用新密码登录（需先启用）
    await client.patch(
        f"/admin/users/{uid}/active", json={"is_active": True}, headers=admin
    )
    await client.post(
        f"/admin/users/{uid}/reset-password",
        json={"new_password": "brandnew123"},
        headers=admin,
    )
    relogin = await client.post(
        "/auth/login", json={"email": "u1@company.com", "password": "brandnew123"}
    )
    assert relogin.status_code == 200

    # 提升为管理员
    prom = await client.patch(
        f"/admin/users/{uid}/role", json={"role": "admin"}, headers=admin
    )
    assert prom.json()["role"] == "admin"


async def test_user_endpoints_admin_only(client, seed_user):
    _, internal = await seed_user("internal")
    assert (await client.get("/admin/users", headers=internal)).status_code == 403


# ── F5 组 + 自动入组 ───────────────────────────────────

async def test_group_rule_auto_membership(client, seed_user, seed_domain):
    _, admin = await seed_user("admin")
    # 建组 + 规则：邮箱后缀 company.com 自动入组
    g = await client.post(
        "/admin/groups", json={"name": "全体员工"}, headers=admin
    )
    gid = g.json()["id"]
    await client.post(
        f"/admin/groups/{gid}/rules",
        json={"field": "email_domain", "op": "equals", "value": "company.com"},
        headers=admin,
    )
    # 注册匹配用户 → 自动入组
    await seed_domain("company.com")
    reg = await client.post(
        "/auth/register", json={"email": "auto@company.com", "password": "longenough1"}
    )
    uid = reg.json()["id"]
    members = await client.get(f"/admin/groups/{gid}/members", headers=admin)
    assert any(m["id"] == uid for m in members.json())


async def test_recompute_memberships(client, seed_user, seed_domain):
    _, admin = await seed_user("admin")
    await seed_domain("company.com")
    reg = await client.post(
        "/auth/register", json={"email": "later@company.com", "password": "longenough1"}
    )
    uid = reg.json()["id"]
    # 先注册，后建规则
    g = await client.post("/admin/groups", json={"name": "后建组"}, headers=admin)
    gid = g.json()["id"]
    await client.post(
        f"/admin/groups/{gid}/rules",
        json={"field": "email_domain", "op": "equals", "value": "company.com"},
        headers=admin,
    )
    # 手动重算 → later 用户入组
    rc = await client.post("/admin/recompute-memberships", headers=admin)
    assert rc.status_code == 200
    members = await client.get(f"/admin/groups/{gid}/members", headers=admin)
    assert any(m["id"] == uid for m in members.json())


# ── F6 RBAC ────────────────────────────────────────────

async def test_group_permissions_and_effective(client, seed_user, db_session):
    from app.models.auth import User
    from app.models.rbac import GroupMember
    from app.services.rbac_service import effective_permissions

    _, admin = await seed_user("admin")
    g = await client.post("/admin/groups", json={"name": "只读组"}, headers=admin)
    gid = g.json()["id"]
    # 设 documents=read
    await client.put(
        f"/admin/groups/{gid}/permissions",
        json={"module": "documents", "level": "read"},
        headers=admin,
    )
    # 造普通用户并入组
    uid = uuid.uuid4()
    from app.core.security import hash_password

    db_session.add(
        User(
            id=uid,
            email=f"{uid.hex[:6]}@company.com",
            password_hash=hash_password("x"),
            role="internal",
        )
    )
    db_session.add(GroupMember(group_id=uuid.UUID(gid), user_id=uid))
    await db_session.commit()

    user = await db_session.get(User, uid)
    perms = await effective_permissions(db_session, user=user)
    assert perms.get("documents") == "read"


async def test_admin_bypasses_rbac(client, seed_user, db_session):
    from app.services.rbac_service import effective_permissions

    admin_id, _ = await seed_user("admin")
    from app.models.auth import User

    user = await db_session.get(User, admin_id)
    perms = await effective_permissions(db_session, user=user)
    # admin 全模块 write
    assert perms["documents"] == "write"
    assert perms["users"] == "write"


# ── F7 空间按组授权 ────────────────────────────────────

async def test_workspace_group_grant_gives_access(client, seed_user, db_session):
    from app.models.auth import User
    from app.models.rbac import GroupMember
    from app.services.workspace_service import is_member

    _, admin = await seed_user("admin")
    ws = await client.post("/workspaces", json={"name": "组空间"}, headers=admin)
    ws_id = ws.json()["id"]
    g = await client.post("/admin/groups", json={"name": "空间组"}, headers=admin)
    gid = g.json()["id"]

    # 造用户入组
    uid = uuid.uuid4()
    from app.core.security import hash_password

    db_session.add(
        User(
            id=uid,
            email=f"{uid.hex[:6]}@company.com",
            password_hash=hash_password("x"),
            role="internal",
        )
    )
    db_session.add(GroupMember(group_id=uuid.UUID(gid), user_id=uid))
    await db_session.commit()

    # 授权前：非成员
    assert await is_member(db_session, workspace_id=uuid.UUID(ws_id), user_id=uid) is False

    # 空间授权给组
    grant = await client.post(
        f"/workspaces/{ws_id}/group-grants",
        json={"group_id": gid, "role_in_ws": "viewer"},
        headers=admin,
    )
    assert grant.status_code == 201

    # 授权后：经组获得访问权
    assert await is_member(db_session, workspace_id=uuid.UUID(ws_id), user_id=uid) is True
